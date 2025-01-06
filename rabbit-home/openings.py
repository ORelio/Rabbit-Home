#!/usr/bin/env python3

# =========================================
# whindows - monitor and query window state
# By ORelio (c) 2024 - CDDL 1.0
# =========================================

from threading import Lock
from configparser import ConfigParser
from enum import Enum

import enocean
import rabbits

from logs import logs
from events import EventHandler

class WindowState(Enum):
    OPEN = 1
    CLOSED = 2
    UNKNOWN = 3

config = ConfigParser()
config.read('config/windows.ini')

_data_lock = Lock()
_window_state = {}

_window_to_device = {}
_device_to_window = {}

_window_to_shutter = {}
_shutter_to_window = {}

_window_to_rabbit = {}
_rabbit_to_windows = {}

# == Load config ==

for name_raw in config.sections():
    name = name_raw.lower()
    device = config.get(name_raw, 'device')
    shutter = config.get(name_raw, 'shutter', fallback=None)
    rabbit = config.get(name_raw, 'rabbit', fallback=None)
    device_data = device.split(':')
    if len(device_data) != 2:
        raise ValueError('Invalid device identifier for {}: "{}". Expecting type:devicename'.format(name, device_data))
    if device_data[0].lower() != 'enocean':
        raise ValueError('Invalid device type for {}: "{}". Currently supported: enocean'.format(name, device_data[0].lower()))
    if name in _window_to_device:
        raise ValueError('Duplicate window name: {}'.format(name))
    if device in _device_to_window:
        raise ValueError('Device mapped to several windows: {}'.format(device))
    if rabbit:
        rabbit = rabbits.get_name(rabbit)
    if shutter:
        shutter = shutter.lower()
    if shutter and shutter in _shutter_to_window:
        raise ValueError('Shutter mapped to several windows: {}'.format(shutter))
    _window_to_device[name] = device
    _device_to_window[device] = name
    if shutter:
        _window_to_shutter[name] = shutter
        _shutter_to_window[shutter] = name
    if rabbit:
        _window_to_rabbit[name] = rabbit
        if not rabbit in _rabbit_to_windows:
            _rabbit_to_windows[rabbit] = []
        if not name in _rabbit_to_windows[rabbit]:
            _rabbit_to_windows[rabbit].append(name)
    logs.debug('Loaded window "{}" (device="{}", shutter="{}", rabbit="{}")'.format(name, device, shutter, rabbit))
for rabbit in _rabbit_to_windows:
    logs.debug('Rabbit "{}" has {} window(s): {}'.format(rabbit, len(_rabbit_to_windows[rabbit]), ', '.join(_rabbit_to_windows[rabbit])))

# == State API ==

def get_current_state(window: str = None, shutter: str = None) -> WindowState:
    '''
    Get current window state by window or shutter name
    Returns current state or UNKNOWN if unknown
    '''
    if (window and shutter) or (not window and not shutter):
        raise ValueError('Specify exactly one argument: window or shutter')
    if shutter:
        window = get_window_from_shutter(shutter)
        if not shutter:
            raise ValueError('Unknown window for shutter: {}'.format(shutter))
    return _window_state.get(shutter, WindowState.UNKNOWN)

# == Data APIs ==

def get_window_from_shutter(shutter: str) -> str:
    '''
    Get window for the specified shutter
    Returns window name or None if no window set for the specified shutter
    '''
    return _shutter_to_window.get(shutter, None)

def get_shutter_from_window(window: str) -> str:
    '''
    Get shutter for the specified window
    Returns shutter name or None if no shutter set for the specified shutter
    '''
    return _shutter_to_window.get(window, None)

def get_rabbit_from_window(window: str) -> str:
    '''
    Get rabbit for the specified shutter
    Returns rabbit name or None if no rabbit set for the specified shutter
    '''
    return _window_to_rabbit.get(window, None)

def get_windows_from_rabbit(rabbit: str) -> list[str]:
    '''
    Get windows for the specified rabbit
    Returns list of shutters for the specified rabbit, [] if none
    '''
    rabbit = rabbits.get_name(rabbit)
    return _rabbit_to_windows.get(shutter, [])

# == Event API ==

'''
Window Event Handler
Callbacks will receive args = (window_name: str, state: WindowState, shutter_name: str = None, rabbit_name: str = None)
'''
event_handler = EventHandler('Windows')

def _enocean_callback(sender_name: str, contact_event: object):
    '''
    Handle enocean switch event:
    Find which button of which switch was pressed, and run the associated action.
    '''
    device = 'enocean:{}'.format(sender_name.lower())
    state = WindowState.CLOSED if contact_event.closed else WindowState.OPEN

    if device in _device_to_window:
        window = _device_to_window[device]
        with _data_lock:
            _window_state[window] = state
        event_handler.dispatch(window, state, get_shutter_from_window(window), get_rabbit_from_window(window))

enocean.contact_event_handler.subscribe(_enocean_callback)
