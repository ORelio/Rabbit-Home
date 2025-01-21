#!/usr/bin/env python3

# ==============================================
# openings - monitor and query window/door state
# By ORelio (c) 2024-2025 - CDDL 1.0
# ==============================================

from threading import Lock
from configparser import ConfigParser
from enum import Enum

import enocean
import rabbits

from logs import logs
from events import EventHandler

class OpenState(Enum):
    OPEN = 1
    CLOSED = 2
    UNKNOWN = 3

config = ConfigParser()
config.read('config/openings.ini')

_data_lock = Lock()
_opening_state = {}

_opening_to_device = {}
_device_to_opening = {}

_opening_to_shutter = {}
_shutter_to_opening = {}

_opening_to_rabbit = {}
_rabbit_to_openings = {}

_front_door = None

# == Load config ==

for name_raw in config.sections():
    name = name_raw.lower()
    device = config.get(name_raw, 'device')
    shutter = config.get(name_raw, 'shutter', fallback=None)
    rabbit = config.get(name_raw, 'rabbit', fallback=None)
    is_front_door = config.getboolean(name_raw, 'frontdoor', fallback=False)
    device_data = device.split(':')
    if len(device_data) != 2:
        raise ValueError('Invalid device identifier for {}: "{}". Expecting type:devicename'.format(name, device_data))
    if device_data[0].lower() != 'enocean':
        raise ValueError('Invalid device type for {}: "{}". Currently supported: enocean'.format(name, device_data[0].lower()))
    if name in _opening_to_device:
        raise ValueError('Duplicate opening name: {}'.format(name))
    if device in _device_to_opening:
        raise ValueError('Device mapped to several openings: {}'.format(device))
    if rabbit:
        rabbit = rabbits.get_name(rabbit)
    if shutter:
        shutter = shutter.lower()
    if shutter and shutter in _shutter_to_opening:
        raise ValueError('Shutter mapped to several openings: {}'.format(shutter))
    if is_front_door and _front_door:
        raise ValueError('Duplicate front door: {}, {}'.format(_front_door, name))
    _opening_to_device[name] = device
    _device_to_opening[device] = name
    if shutter:
        _opening_to_shutter[name] = shutter
        _shutter_to_opening[shutter] = name
    if rabbit:
        _opening_to_rabbit[name] = rabbit
        if not rabbit in _rabbit_to_openings:
            _rabbit_to_openings[rabbit] = []
        if not name in _rabbit_to_openings[rabbit]:
            _rabbit_to_openings[rabbit].append(name)
    if is_front_door:
        _front_door = name
    logs.debug('Loaded opening "{}" (device="{}", shutter="{}", rabbit="{}", frontdoor="{}")'.format(name, device, shutter, rabbit, is_front_door))
for rabbit in _rabbit_to_openings:
    logs.debug('Rabbit "{}" has {} opening(s): {}'.format(rabbit, len(_rabbit_to_openings[rabbit]), ', '.join(_rabbit_to_openings[rabbit])))

# == State API ==

def get_current_state(opening: str = None, shutter: str = None) -> OpenState:
    '''
    Get current opening state by opening or shutter name
    Returns current state or UNKNOWN if unknown
    '''
    if (opening and shutter) or (not opening and not shutter):
        raise ValueError('Specify exactly one argument: opening or shutter')
    if shutter:
        opening = get_opening_from_shutter(shutter)
        if not shutter:
            raise ValueError('Unknown opening for shutter: {}'.format(shutter))
    return _opening_state.get(shutter, OpenState.UNKNOWN)

# == Data APIs ==

def get_opening_from_shutter(shutter: str) -> str:
    '''
    Get opening for the specified shutter
    Returns opening name or None if no opening set for the specified shutter
    '''
    return _shutter_to_opening.get(shutter, None)

def get_shutter_from_opening(opening: str) -> str:
    '''
    Get shutter for the specified opening
    Returns shutter name or None if no shutter set for the specified shutter
    '''
    return _shutter_to_opening.get(opening, None)

def get_rabbit_from_opening(opening: str) -> str:
    '''
    Get rabbit for the specified shutter
    Returns rabbit name or None if no rabbit set for the specified shutter
    '''
    return _opening_to_rabbit.get(opening, None)

def get_openings_from_rabbit(rabbit: str) -> list[str]:
    '''
    Get openings for the specified rabbit
    Returns list of shutters for the specified rabbit, [] if none
    '''
    rabbit = rabbits.get_name(rabbit)
    return _rabbit_to_openings.get(shutter, [])

# == Event API ==

'''
Opening Event Handler
Callbacks will receive args = (opening_name: str, state: OpenState, shutter_name: str = None, rabbit_name: str = None, is_front_door: bool = False)
'''
event_handler = EventHandler('Openings')

def _enocean_callback(sender_name: str, contact_event: object):
    '''
    Handle enocean switch event:
    Find which button of which switch was pressed, and run the associated action.
    '''
    device = 'enocean:{}'.format(sender_name.lower())
    state = OpenState.CLOSED if contact_event.close else OpenState.OPEN

    if device in _device_to_opening:
        opening_name = _device_to_opening[device]
        with _data_lock:
            _opening_state[opening_name] = state
        event_handler.dispatch(opening_name, state, get_shutter_from_opening(opening_name), get_rabbit_from_opening(opening_name), opening_name == _front_door)

enocean.contact_event_handler.subscribe(_enocean_callback)
