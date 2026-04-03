#!/usr/bin/env python3

# =================================================================================
# sensorhealth - Monitor sensor health and warn about lost sensors or low batteries
# By ORelio (c) 2026 - CDDL 1.0
# =================================================================================

from threading import Thread, Lock

import time

from logs import logs

import notifications
import rabbits

_data_lock = Lock()

_sensor_list = list()
_sensor_to_type = dict()
_sensor_to_name = dict()
_sensor_to_timeout = dict()
_sensor_to_rabbit = dict()
_sensor_to_tag = dict()

_health_monitoring_thread_started = False
_last_battery_warning_for_sensor = dict()
_last_heatbeat_from_sensor = dict()

# === Sensor health monitoring ===

def _get_additional_tag(device: str):
    '''
    (internal) get additional tag describing device type for notifications
    '''
    tag = _sensor_to_tag.get(device, None)
    if tag:
        return ',{}'.format(tag)
    else:
        return ''

def _get_device_id(device_type: str, device_name: str):
    '''
    (internal) compute device ID from device type and name
    '''
    return '{}_{}'.format(device_type.lower(), device_name.lower())

def _sensor_health_monitoring_thread():
    '''
    Monitor sensor heartbeats to make sure sensors are still sending data. If not, generate an alert
    '''
    lost_sensors = dict()
    initial_delay = 120
    loop_delay = 30

    with _data_lock:
        device_with_max_timeout = max(_sensor_to_timeout, key=_sensor_to_timeout.get)
        initial_delay = max(_sensor_to_timeout[device_with_max_timeout], 120)
        device_with_min_timeout = min(_sensor_to_timeout, key=_sensor_to_timeout.get)
        loop_delay = max(_sensor_to_timeout[device_with_min_timeout] / 2, 30)

    # leave time for sensors to send initial data
    time.sleep(initial_delay)

    while True:
        time.sleep(loop_delay)
        with _data_lock:
            for device in _sensor_to_timeout:
                dev_type = _sensor_to_type[device]
                dev_name = _sensor_to_name[device]
                timeout = _sensor_to_timeout[device]
                rabbit = _sensor_to_rabbit[device]
                if not device in lost_sensors:
                    if not device in _last_heatbeat_from_sensor or _last_heatbeat_from_sensor[device] < (time.time() - timeout):
                        lost_sensors[device] = True
                        logs.warning('No heartbeat from sensor: {} ({})'.format(dev_name, dev_type))
                        notifications.publish(
                            "Pas de réception : {} ({})".format(dev_name, dev_type),
                            title='Capteur hors service',
                            tags='x{}'.format(_get_additional_tag(device)),
                            rabbit=rabbit)
                else:
                    if device in _last_temperature_time and _last_temperature_time[device] > (time.time() - timeout):
                        del lost_sensors[device]
                        logs.info('Sensor is back: {} ({})'.format(dev_name, dev_type))
                        notifications.publish(
                            "Capteur revenu : {} ({})".format(dev_name, dev_type),
                            title='Capteur opérationnel',
                            tags='heavy_check_mark{}'.format(_get_additional_tag(device)),
                            rabbit=rabbit)

# === API for other modules ===

def register(device_type: str, device_name: str, timeout_seconds: int, rabbit: str = None, device_tag: str = None):
    '''
    Register a new sensor to monitor
    device_type: Type of the device for telling apart devices with same name (e.g. temperature sensor 'living_room' vs motion sensor 'living_room')
    device_name: Name of the device to monitor
    timeout_seconds: maximum delay without heartbeat, sensor will be considered lost if reaching timeout
    rabbit: (optional) rabbit associated with the device, for use with notifications
    device_tag: (optional) tag describing device type (for notifications, see 'tags' arg for 'publish()' in notifications.py)
    '''
    global _health_monitoring_thread_started
    device = _get_device_id(device_type, device_name)
    if timeout_seconds < 60:
        raise ValueError('[SensorHealth] Timeout too short: {} (minium 60 seconds)'.format(timeout_seconds))
    if rabbit:
        rabbit = rabbits.get_name(rabbit)
    with _data_lock:
        if device in _sensor_to_timeout:
            raise ValueError('[SensorHealth] Duplicate device or already registered: "{}"'.format(device))
        _sensor_list.append(device)
        _sensor_to_type[device] = device_type
        _sensor_to_name[device] = device_name
        _sensor_to_timeout[device] = timeout_seconds
        _sensor_to_rabbit[device] = rabbit
        _sensor_to_tag[device] = device_tag
        logs.debug('Registered: device={}, timeout={}, rabbit={}, tag={}'.format(device, timeout_seconds, rabbit, device_tag))
        if not _health_monitoring_thread_started:
            logs.debug('Registered first device, starting sensor health monitor thread')
            _health_monitoring_thread_started = True
            _health_monitoring_thread = Thread(target=_sensor_health_monitoring_thread, name='Sensor health monitor')
            _health_monitoring_thread.start()

def heartbeat(device_type: str, device_name: str, battery_low: bool = False):
    '''
    Signal a heartbeat, resetting timeout for the specified device.
    device_type: Type of the device for telling apart devices with same name (e.g. temperature sensor 'living_room' vs motion sensor 'living_room')
    device_name: Name of the device to monitor
    battery_low: (optional) signal low battery
    '''
    device = _get_device_id(device_type, device_name)
    with _data_lock:
        if device in _sensor_to_timeout:
            _last_heatbeat_from_sensor[device] = time.time()
            if battery_low:
                logs.warning('Battery low for device: {}'.format(device))
                if _last_battery_warning_for_sensor.get(device, 0) < time.time() - 86400: # wait 24 hours before re-issuing warning
                    _last_battery_warning_for_sensor[device] = time.time()
                    notifications.publish('{}'.format(device), title='Pile faible', tags='battery{}'.format(_get_additional_tag(device)), rabbit=_device_to_rabbit.get(device, None))
        else:
            logs.warning('Device "{}" not registered for health monitoring'.format(device))
