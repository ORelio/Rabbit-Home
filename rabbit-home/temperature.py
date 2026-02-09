#!/usr/bin/env python3

# ======================================================================================================================
# temperature - Retrieve temperature from enocean sensors/weather forecast and generate temperature events for scenarios
# By ORelio (c) 2024 - CDDL 1.0
# ======================================================================================================================

from flask import Blueprint, jsonify
from configparser import ConfigParser
from dataclasses import dataclass
from threading import Thread, Lock
from typing import Callable
from enum import Enum

import time

import enocean
import rabbits
import weather
import notifications

from events import EventHandler
from logs import logs

_device_outside = None

_device_to_correction = dict()
_device_to_name = dict()
_name_to_device = dict()

_rabbit_to_device = dict()
_device_to_rabbit = dict()
_device_to_rabbit_secondary = dict()

_last_temperature_value = dict()
_last_temperature_outside = None
_last_temperature_time = dict()
_last_temperature_time_lock = Lock()

_threshold_cold_forecast = 0
_threshold_cold_outside = 5
_threshold_cold_inside = 15
_threshold_hot_inside = 25
_threshold_hot_outside = 30
_threshold_hot_forecast = 35

class TemperatureEventType(Enum):
    DATA = 1
    COLD = 2
    NORMAL = 3
    HOT = 4

@dataclass
class TemperatureEvent():
    type: TemperatureEventType
    temperature: float
    sensor: str
    rabbit: str
    outside: bool

_state_outside = TemperatureEventType.NORMAL
_state_inside_by_rabbit = dict()
_state_inside_by_sensor = dict()

# === Load config and import relevant modules ===

config = ConfigParser()
config.read('config/temperature.ini')
for sensor in config.sections():
    name = sensor.lower()
    if name == 'thresholds':
        _threshold_cold_forecast = config.getfloat(sensor, 'forecast_cold', fallback=0)
        _threshold_cold_outside = config.getfloat(sensor, 'outdoors_cold', fallback=5)
        _threshold_cold_inside = config.getfloat(sensor, 'indoors_cold', fallback=16)
        _threshold_hot_inside = config.getfloat(sensor, 'indoors_hot', fallback=25)
        _threshold_hot_outside = config.getfloat(sensor, 'outdoors_hot', fallback=30)
        _threshold_hot_forecast = config.getfloat(sensor, 'forecast_hot', fallback=35)
        assert(_threshold_cold_forecast < _threshold_cold_outside)
        assert(_threshold_cold_outside < _threshold_cold_inside)
        assert(_threshold_cold_inside < _threshold_hot_inside)
        assert(_threshold_hot_inside < _threshold_hot_outside)
        assert(_threshold_hot_outside < _threshold_hot_forecast)
    else:
        device = config.get(sensor, 'device', fallback=None)
        devtype = config.get(sensor, 'type', fallback=None)
        devrabbit = config.get(sensor, 'rabbit', fallback=None)
        devrabbit_secondary = config.get(sensor, 'rabbit_secondary', fallback=None)
        correction = config.getfloat(sensor, 'correction', fallback=0)
        if device is None:
            raise ValueError('[Temperature] Missing "device" field for "{}"'.format(sensor))
        device = device.lower()
        if device in _device_to_correction:
            raise ValueError('[Temperature] Duplicate device: "{}"'.format(device))
        if devtype:
            if devtype.lower() == 'outside':
                if _device_outside:
                    raise ValueError('[Temperature] Duplicate outside devices: "{}", "{}"'.format(device, _device_outside))
                _device_outside = device
            else:
                raise ValueError('[Temperature] Unknown "type" field for "{}"'.format(sensor))
        _device_to_correction[device] = correction
        _device_to_name[device] = name
        _name_to_device[name] = device
        if devrabbit:
            devrabbit = rabbits.get_name(devrabbit)
            if devrabbit in _rabbit_to_device:
                raise ValueError('[Temperature] Multiple sensors for rabbit "{}": "{}", "{}". Use rabbit_secondary for secondary sensors.'.format(
                    devrabbit, device, _device_to_rabbit[device]))
            _rabbit_to_device[devrabbit] = device
            _device_to_rabbit[device] = devrabbit
        if devrabbit_secondary:
            devrabbit_secondary = rabbits.get_name(devrabbit_secondary)
            _device_to_rabbit_secondary[device] = devrabbit_secondary
        logs.debug('Loaded sensor {} (device={}, correction={}, type={}, rabbit={}, rabbit_secondary={})'.format(
            name, device, correction, devtype, devrabbit, devrabbit_secondary))

logs.debug((
        'Thresholds: forecast_cold={}°C, outdoors_cold={}°C, indoors_cold={}°C, '
         + 'indoors_hot={}°C, outdoors_hot={}°C, forecast_hot={}°C'
    ).format(
        _threshold_cold_forecast, _threshold_cold_outside, _threshold_cold_inside,
        _threshold_hot_inside, _threshold_hot_outside, _threshold_hot_forecast
    )
)

# === Temperature API for other modules ===

'''
Temperature Event Handler
Callbacks will receive args = TemperatureEvent
'''
event_handler = EventHandler('Temperature')

def get_temperature_outside() -> float:
    '''
    Get current temperature outside
    returns temperature or None if data is unavailable
    '''
    if _device_outside is None:
        return weather.get_current_temperature()
    return _last_temperature_outside

def get_state_outside() -> TemperatureEventType:
    '''
    Get current temperature state outside
    returns temperature state (NORMAL, HOT or COLD) or NORMAL if data is unavailable
    '''
    return _state_outside

def get_state_today() -> TemperatureEventType:
    '''
    Get today temperature state according to weather forecast or current temperature
    returns temperature state (NORMAL, HOT or COLD) or NORMAL if data is unavailable
    '''
    weather_forecast_min = weather.get_today_minimum_temperature()
    weather_forecast_max = weather.get_today_maximum_temperature()
    if weather_forecast_min and weather_forecast_min < _threshold_cold_forecast:
        return TemperatureEventType.COLD
    if weather_forecast_max and weather_forecast_max > _threshold_hot_forecast:
        return TemperatureEventType.HOT
    return get_state_outside()

def _get_temperature_value(sensor: str = None, rabbit: str = None, return_state: bool = False) -> float:
    '''
    Get current temperature for the specified sensor or rabbit
    return_state: if set, return TemperatureEventType. Otherwise, return temperature as float.
    returns temperature or None if data is unavailable
    '''
    if sensor is None and rabbit is None:
        raise ValueError('[Temperature] Missing argument, please specify either sensor or rabbit.')
    if sensor and rabbit:
        raise ValueError('[Temperature] Too many arguments, please specify either sensor or rabbit.')
    device = None
    rabbit_name = None
    if rabbit:
        rabbit_name = rabbits.get_name(rabbit)
        if rabbit_name in _rabbit_to_device:
            device = _rabbit_to_device[rabbit_name]
    if rabbit and not device:
        raise ValueError('[Temperature] Could not find sensor for rabbit: {}'.format(rabbit))
    if not device:
        device = _name_to_device.get(sensor.lower(), None)
        if not device:
            raise ValueError('[Temperature] Unknown sensor: {}'.format(sensor))
    if return_state:
        if rabbit_name:
            return _state_inside_by_rabbit.get(rabbit_name, TemperatureEventType.NORMAL)
        return _state_inside_by_sensor.get(device, TemperatureEventType.NORMAL)
    return _last_temperature_value.get(device, None)

def get_temperature(sensor = None, rabbit = None) -> float:
    '''
    Get current temperature for the specified sensor or rabbit
    returns temperature or None if data is unavailable
    '''
    return _get_temperature_value(sensor=sensor, rabbit=rabbit, return_state=False)

def get_state(sensor = None, rabbit = None) -> TemperatureEventType:
    '''
    Get current temperature state the specified sensor or rabbit
    returns temperature state (NORMAL, HOT or COLD) or NORMAL if data is unavailable
    '''
    return _get_temperature_value(sensor=sensor, rabbit=rabbit, return_state=True)

# == Temperature threshold monitoring ==

def _threshold_check(outside: bool, current_state: TemperatureEventType, current_temperature: float) -> TemperatureEventType:
    '''
    Determine if the specified temperature crossed a threshold
    Returns a TemperatureEventType if a threshold was crossed, or None if nothing happened
    '''
    threshold_cold = _threshold_cold_outside if outside else _threshold_cold_inside
    threshold_hot = _threshold_hot_outside if outside else _threshold_hot_inside

    # In case of unfavorable weather today, adjust thresholds to match indoors temperature closely
    if outside:
        weather_forecast_min = weather.get_today_minimum_temperature()
        weather_forecast_max = weather.get_today_maximum_temperature()
        if (weather_forecast_min and weather_forecast_min < _threshold_cold_forecast) \
          or (weather_forecast_max and weather_forecast_max > _threshold_hot_forecast):
            indoors_data_available = True
            indoors_minimum_temperature = None
            indoors_maximum_temperature = None
            for device in _device_to_name:
                device_temp_data = _last_temperature_value.get(device, None)
                if not device_temp_data:
                    indoors_data_available = False
                else:
                    if not indoors_minimum_temperature or device_temp_data < indoors_minimum_temperature:
                        indoors_minimum_temperature = device_temp_data
                    if not indoors_maximum_temperature or device_temp_data > indoors_maximum_temperature:
                        indoors_maximum_temperature = device_temp_data
            if indoors_data_available:
                threshold_cold = indoors_minimum_temperature
                threshold_hot = indoors_maximum_temperature
            else:
                threshold_cold = _threshold_cold_inside
                threshold_hot = _threshold_hot_inside

    if current_state == TemperatureEventType.NORMAL:
        if current_temperature < threshold_cold - 0.25:
            return TemperatureEventType.COLD
        if current_temperature > threshold_hot + 0.25:
            return TemperatureEventType.HOT
    else:
        if (current_temperature > threshold_cold + 0.25 and current_state == TemperatureEventType.COLD) \
          or (current_temperature < threshold_hot - 0.25 and current_state == TemperatureEventType.HOT):
            return TemperatureEventType.NORMAL

def _event_threshold_generator(event: TemperatureEvent):
    '''
    Monitor DATA events and generate additional temperature events (COLD, HOT, back to NORMAL) when needed
    '''
    global _state_outside
    state_change = None

    if event.type != TemperatureEventType.DATA:
        return

    if event.outside:
        state_change = _threshold_check(True, _state_outside, event.temperature)
        if state_change:
            _state_outside = state_change
    else:
        if event.rabbit:
            if not event.rabbit in _state_inside_by_rabbit:
                _state_inside_by_rabbit[event.rabbit] = TemperatureEventType.NORMAL
            state_change = _threshold_check(False, _state_inside_by_rabbit[event.rabbit], event.temperature)
            if state_change:
                _state_inside_by_rabbit[event.rabbit] = state_change
        else:
            if not event.sensor in _state_inside_by_sensor:
                _state_inside_by_sensor[event.sensor] = TemperatureEventType.NORMAL
            state_change = _threshold_check(False, _state_inside_by_sensor[event.sensor], event.temperature)
            if state_change:
                _state_inside_by_sensor[event.sensor] = state_change

    if state_change:
        event_handler.dispatch(TemperatureEvent(state_change, event.temperature, event.sensor, event.rabbit, event.outside))

event_handler.subscribe(_event_threshold_generator)

# === Enocean Temperature callbacks ===

def enocean_callback(sender_name: str, event: object):
    '''
    Handle enocean temperature events
    '''
    device = 'enocean:{}'.format(sender_name.lower())
    # Retrieve configuration for device which fired the event
    if device in _device_to_name:
        sensor = _device_to_name[device]
        rabbit = _device_to_rabbit.get(device, None)
        outside = (device == _device_outside)
        correction = _device_to_correction[device]
        raw_temperature = event.temperature
        temperature = round(raw_temperature + correction, 2)
        _last_temperature_value[device] = temperature
        with _last_temperature_time_lock:
            _last_temperature_time[device] = time.time()
        if outside:
            _last_temperature_outside = temperature
        event_handler.dispatch(TemperatureEvent(TemperatureEventType.DATA, temperature, sensor, rabbit, outside))
    else:
        logs.warning('No config for device "{}"'.format(device))

enocean.temperature_event_handler.subscribe(enocean_callback)

# === Weather temperature monitoring ===

def temperature_monitoring_thread():
    '''
    Monitor outdoors temperature from weather forecast and generate events based on that every 30 minutes.
    This is a fallack when there is no defined outside sensor in configuration, or sensor has not sent data yet.
    '''
    if _device_outside is None:
        logs.warning('No outside sensor, using weather forecast instead'.format(device))
        while True:
            temperature = get_temperature_outside()
            if temperature:
                event_handler.dispatch(TemperatureEvent(TemperatureEventType.DATA, temperature, 'weather_forecast', None, True))
            time.sleep(1800)
    else:
        logs.debug('Using weather forecast value while waiting for sensor'.format(device))
        temperature = weather.get_current_temperature()
        if temperature:
            event_handler.dispatch(TemperatureEvent(TemperatureEventType.DATA, temperature, 'weather_forecast', None, True))

_forecast_monitoring_thread = Thread(target=temperature_monitoring_thread, name='Temperature forecast monitor')
_forecast_monitoring_thread.start()

# === Sensor health monitoring ===

def sensor_health_monitoring_thread():
    '''
    Monitor sensor data timestamps to make sure sensors are still sending data. If not, generate an alert
    '''
    _lost_sensors = dict()
    time.sleep(4200) # leave time for sensors to send initial data
    while True:
        time.sleep(2400)
        with _last_temperature_time_lock:
            for device in _device_to_name:
                name = _device_to_name[device]
                if not device in _lost_sensors:
                    if not device in _last_temperature_time or _last_temperature_time[device] < (time.time() - 4200):
                        _lost_sensors[device] = True
                        logs.warning('No data from sensor: {} ({})'.format(name, device))
                        notifications.publish(
                            "Pas de réception : {}".format(name),
                            title='Capteur hors service',
                            tags='x,thermometer',
                            rabbit=_device_to_rabbit.get(device, _device_to_rabbit_secondary.get(device, None)))
                else:
                    if device in _last_temperature_time and _last_temperature_time[device] > (time.time() - 4200):
                        del _lost_sensors[device]
                        logs.info('Sensor is back: {} ({})'.format(name, device))
                        notifications.publish(
                            "Capteur revenu : {}".format(name),
                            title='Capteur opérationnel',
                            tags='heavy_check_mark,thermometer',
                            rabbit=_device_to_rabbit.get(device, _device_to_rabbit_secondary.get(device, None)))

if len(_device_to_name) > 0:
    _health_monitoring_thread = Thread(target=sensor_health_monitoring_thread, name='Temperature sensor health monitor')
    _health_monitoring_thread.start()

# === HTTP API ===

temperature_api = Blueprint('temperature_api', __name__)

@temperature_api.route('/api/v1/temperature', methods = ['GET'])
def temperature_api_get():
    device_info = {}
    for device in _device_to_name:
        device_info[_device_to_name[device]] = {
            'temperature': _last_temperature_value.get(device, None),
            'time': _last_temperature_time.get(device, None),
        }
    return jsonify(device_info)
