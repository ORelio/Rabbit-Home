#!/usr/bin/env python3

# =============================================================================================
# motion - Retrieve motion events from enocean sensors and generate motion events for scenarios
# By ORelio (c) 2026 - CDDL 1.0
# =============================================================================================

from flask import Blueprint, jsonify
from configparser import ConfigParser
from dataclasses import dataclass
from threading import Lock

import time

from events import EventHandler
from logs import logs

import enocean
import rabbits
import sensorhealth

_name_to_device = dict()
_device_to_name = dict()
_device_to_rabbit = dict()
_device_is_outside = dict()

_last_motion_time_by_device = dict()
_last_motion_time_by_rabbit = dict()
_last_motion_lock = Lock()

@dataclass
class MotionEvent():
    sensor: str
    rabbit: str
    outside: bool

# === Load config ===

config = ConfigParser()
config.read('config/motion.ini')
for sensor in config.sections():
    name = sensor.lower()
    device = config.get(sensor, 'device', fallback=None)
    devoutside = config.getboolean(sensor, 'outside', fallback=False)
    devrabbit = config.get(sensor, 'rabbit', fallback=None)
    if device is None:
        raise ValueError('[Motion] Missing "device" field for "{}"'.format(sensor))
    device = device.lower()
    if name in _name_to_device:
        raise ValueError('[Motion] Duplicate entry: "{}"'.format(device))
    if device in _device_to_name:
        raise ValueError('[Motion] Duplicate device: "{}"'.format(device))
    _device_to_name[device] = name
    _name_to_device[name] = device
    _device_is_outside[device] = devoutside
    if devrabbit:
        devrabbit = rabbits.get_name(devrabbit)
        _device_to_rabbit[device] = devrabbit
    logs.debug('Loaded sensor {} (device={}, outside={}, rabbit={})'.format(name, device, devoutside, devrabbit))
    sensorhealth.register('motion', name, timeout_seconds=4200, rabbit=devrabbit, device_tag='trackball')

# === Motion API for other modules ===

'''
Motion Event Handler
Callbacks will receive args = MotionEvent
'''
event_handler = EventHandler('Motion')

def get_last_motion_time(sensor: str = None, rabbit: str = None) -> float:
    '''
    Get last motion timestamp (time.time()) for the specified sensor or rabbit
    '''
    if sensor is None and rabbit is None:
        raise ValueError('[Motion] Missing argument, please specify either sensor or rabbit.')
    if sensor and rabbit:
        raise ValueError('[Motion] Too many arguments, please specify either sensor or rabbit.')
    with _last_motion_lock:
        if rabbit:
            return _last_motion_time_by_rabbit.get(rabbit, 0)
        return _last_motion_time_by_device.get(device, 0)

# === Enocean Motion callbacks ===

def enocean_callback(sender_name: str, event: object):
    '''
    Handle enocean motion events
    '''
    device = 'enocean:{}'.format(sender_name.lower())
    # Retrieve configuration for device which fired the event
    if device in _device_to_name:
        sensor = _device_to_name[device]
        rabbit = _device_to_rabbit.get(device, None)
        outside = _device_is_outside[device]
        if event.motion:
            with _last_motion_lock:
                _last_motion_time_by_device[device] = _last_motion_time_by_rabbit[device] = time.time()
            event_handler.dispatch(MotionEvent(sensor, rabbit, outside))
        sensorhealth.heartbeat('motion', sensor, battery_low=event.battery_low)
    else:
        logs.warning('No config for device "{}"'.format(device))

enocean.motion_event_handler.subscribe(enocean_callback)

# === HTTP API ===

motion_api = Blueprint('motion_api', __name__)

@motion_api.route('/api/v1/motion', methods = ['GET'])
def motion_api_get():
    response = {}
    with _last_motion_lock:
        for device in _device_to_name:
            refreshed = int(_last_motion_time_by_device.get(device, 0))
            response[_device_to_name[device]] = {
                'refreshed': refreshed if refreshed > 0 else None
            }
    return jsonify(response)
