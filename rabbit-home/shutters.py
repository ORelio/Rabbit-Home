#!/usr/bin/env python3

# ===========================================================================
# shutters - manage Yokis-Hack shutters: https://github.com/nmaupu/yokis-hack
# Uses 'shuttercmd' command to connect to the microcontroller over serial
# See utilities/shuttercmd folder for source code and setup instructions
# To use another shutter protocol, edit _send_command() function below
# By ORelio (c) 2023-2025 - CDDL 1.0
# ===========================================================================

from threading import Thread, Lock
from configparser import ConfigParser
from enum import Enum

import subprocess
import time

from logs import logs

import datastore

_shutters = {}
_shutter_locks = {}
_shutter_thread_tokens = {}
_shutter_delay_close = {}
_shutter_closed_offset = {}
_shutter_delay_open = {}
_shutter_halfway = {}
_command_lock = Lock()

_SHUTTER_STATE_DATASTORE = 'shutters.state_percent'
_shutter_state_percent = datastore.get(_SHUTTER_STATE_DATASTORE, {})

class ShutterState(Enum):
    OPEN = 1
    CLOSE = 2
    STOP = 3
    HALF = 4
    AUTO = 5

_shutter_state_to_command = {
    ShutterState.OPEN: 'on',
    ShutterState.CLOSE: 'off',
    ShutterState.STOP: 'pause'
}

_SHUTTER_COMMAND="shuttercmd"
_SHUTTER_ARGUMENT="{STATE} {SHUTTER}"
_SEND_COMMAND_DELAY=0.1
_START_MOVING_DELAY=0.5

config = ConfigParser()
config.read('config/shutters.ini')

# Load configuration file
for shutter_name_raw in config.sections():
    shutter_alias = shutter_name_raw.lower()
    shutter_internal_name = config.get(shutter_name_raw, 'name')
    shutter_close_delay = config.getfloat(shutter_name_raw, 'close', fallback=None)
    shutter_closed_offset = config.getfloat(shutter_name_raw, 'offset', fallback=None)
    shutter_open_delay = config.getfloat(shutter_name_raw, 'open', fallback=None)
    shutter_half_open = config.getint(shutter_name_raw, 'halfway', fallback=50)
    if shutter_alias in _shutters:
        raise ValueError('Duplicate shutter alias: {}'.format(shutter_alias))
    _shutters[shutter_alias] = shutter_internal_name
    if (shutter_close_delay or shutter_closed_offset or shutter_open_delay) \
       and None in [shutter_open_delay, shutter_closed_offset, shutter_open_delay]:
        raise ValueError('Shutter {}: Please define close/offset/open, or none of each'.format(shutter_alias))
    if shutter_close_delay:
        if shutter_close_delay < 0:
            shutter_close_delay = 0
        if shutter_closed_offset < 0:
            shutter_closed_offset = 0
        if shutter_open_delay < 0:
            shutter_open_delay = 0
        _shutter_delay_close[shutter_alias] = shutter_close_delay
        _shutter_closed_offset[shutter_alias] = shutter_closed_offset
        _shutter_delay_open[shutter_alias] = shutter_open_delay
    if shutter_half_open < 0:
        shutter_half_open = 0
    if shutter_half_open > 99:
        shutter_half_open = 99
    _shutter_halfway[shutter_alias] = shutter_half_open
    _shutter_locks[shutter_alias] = Lock()
    logs.debug('Loaded shutter "{}" (name={}, close={}, offset={}, open={}, halfway={}% closed)'.format(
        shutter_alias,
        shutter_internal_name,
        shutter_close_delay,
        shutter_closed_offset,
        shutter_open_delay,
        int(shutter_half_open)
    ))
logs.debug('Loaded {} shutter definitions'.format(len(_shutters)))

def get_full_length_delay(shutter: str, state: ShutterState) -> float:
    '''
    Get maximum delay in seconds for moving shutter from 0 to 99 (CLOSE) or 99 to 0 (OPEN)
    shutter: Name of shutter to operate
    state: Target shutter state, assuming we are currenlty in the opposite state
    '''
    if state == ShutterState.OPEN:
        return _shutter_delay_open.get(shutter, None)
    if state == ShutterState.CLOSE:
        return _shutter_delay_close.get(shutter, None)
    return None

def get_halfway_percent(shutter: str) -> int:
    '''
    Get configured state percent for ShutterState.HALF of desired shutter
    shutter: Name of shutter
    '''
    return _shutter_halfway.get(shutter, None)

def get_closed_offset_delay(shutter: str) -> float:
    '''
    Get delay in seconds for moving shutter from 99% (closed with blades open) to 100% (fully closed)
    shutter: Name of shutter to operate
    '''
    return _shutter_closed_offset.get(shutter, None)

def get_current_state(shutter: str) -> ShutterState:
    '''
    Get current shutter state
    Note: does not support shutters with state feedback feature
    This returns the last operated state, which may not match if the shutter was operated manually
    Returns current state or STOP if unknown
    '''
    state_percent = _shutter_state_percent.get(shutter, None)
    if state_percent is None:
        return ShutterState.STOP
    if state_percent <= 0:
        return ShutterState.OPEN
    elif state_percent >= 100:
        return ShutterState.CLOSE
    elif state_percent == get_halfway_percent(shutter):
        return ShutterState.HALF
    else:
        return ShutterState.STOP

def get_current_state_percent(shutter: str) -> int:
    '''
    Get current shutter state in percent between 0 (open) and 100 (fully closed)
    Note: does not support shutters with state feedback feature
    This returns the last operated height, which may not match if the shutter was operated manually
    Returns current height between 0 (open) and 100 (closed) or None if unknown
    '''
    state = _shutter_state_percent.get(shutter, None)
    if state is None:
        return None
    if state < 0:
        return 0
    if state > 100:
        return 100
    return state

def _send_command(shutter: str, state: ShutterState):
    '''
    Send command to a shutter
    shutter: Name of shutter to operate
    state: Desired shutter state
    '''
    shutter = shutter.lower()
    if not shutter in _shutters:
        raise ValueError('Unknown shutter: ' + str(shutter))
    if not state in _shutter_state_to_command:
        raise ValueError('Unknwon internal command for ShutterState "{}"'.format(state, shutter))
    state = _shutter_state_to_command[state]
    shutter = _shutters[shutter]
    logs.debug('Setting state {} to shutter {}'.format(state.upper(), shutter))
    with _command_lock:
        subprocess.run([
            _SHUTTER_COMMAND,
            _SHUTTER_ARGUMENT.replace('{STATE}', state).replace('{SHUTTER}', shutter)
        ])
        time.sleep(_SEND_COMMAND_DELAY) # Avoid overloading shutters with too many commands in a row

def _send_command_from_thread(shutter: str, state: str, thread_token: int):
    '''
    Send command to a shutter, acquiring lock and validating thread token
    shutter: Name of shutter to operate
    state: Desired shutter state
    thread_token: Only send command if the current token matches the provided one
    '''
    if _shutter_thread_tokens[shutter] == thread_token:
        with _shutter_locks[shutter]:
            _send_command(shutter, state)

def _update_state_percent_from_thread(shutter: str, state_percent: int, thread_token: int):
    '''
    Update state (percent) of a shutter if thread token validates
    shutter: Name of shutter to operate
    state: New shutter state
    thread_token: Only update state if the current token matches the provided one
    '''
    if state_percent < 0:
        state_percent = 0
    if state_percent > 100:
        state_percent = 100

    if _shutter_thread_tokens[shutter] == thread_token:
        with _shutter_locks[shutter]:
            _shutter_state_percent[shutter] = state_percent
            datastore.set(_SHUTTER_STATE_DATASTORE, _shutter_state_percent)

def _move_to_state_percent(shutter: str, desired_state_percent: int, thread_token: int):
    '''
    Operate a shutter to the desired height
    shutter: Name of shutter to operate
    desired_state_percent: Desired height from 0 (open) to 100 (fully closed)
    thread_token: Stop operating shutters if another operation changes the token
    '''
    assert isinstance(desired_state_percent, int)

    if desired_state_percent < 0:
        desired_state_percent = 0
    if desired_state_percent > 100:
        desired_state_percent = 100

    current_state = get_current_state_percent(shutter)
    logs.info('Adjusting {} from {}% to {}%'.format(shutter, current_state, desired_state_percent))

    if current_state is None:
        target_initial_state = ShutterState.OPEN if desired_state_percent <= 50 else ShutterState.CLOSE
        target_initial_percent = 0 if desired_state_percent <= 50 else 100
        logs.debug('Initial state Unknown, Adjusting {} to {} ({}%)'.format(shutter, target_initial_state, target_initial_percent))
        _send_command_from_thread(shutter, target_initial_state, thread_token)
        target_initial_delay = get_full_length_delay(shutter, target_initial_state) + get_closed_offset_delay(shutter) + 1
        if _shutter_thread_tokens[shutter] == thread_token:
            logs.debug('Sleep: {}s (??? -> {}%)'.format(round(target_initial_delay, 3), target_initial_percent))
        time.sleep(target_initial_delay)
        _update_state_percent_from_thread(shutter, target_initial_percent, thread_token)
        current_state = target_initial_percent

    if current_state == desired_state_percent:
        if _shutter_thread_tokens[shutter] == thread_token:
            logs.debug('Current state for {} is equal to desired state: {}%'.format(shutter, current_state))
        # Does not hurt to send command anyway for fully open/closed states, can fix desync
        if desired_state_percent == 0:
            _send_command_from_thread(shutter, ShutterState.OPEN, thread_token)
        if desired_state_percent == 100:
            _send_command_from_thread(shutter, ShutterState.CLOSE, thread_token)
        return

    direction = ShutterState.OPEN if desired_state_percent < current_state else ShutterState.CLOSE
    one_percent_delay = get_full_length_delay(shutter, direction) / 99 # steps between OPEN and 99% (closed with blades open)
    increment = -1 if direction == ShutterState.OPEN else 1

    if (current_state == 100 and increment == -1) or (current_state == 99 and increment == 1):
        first_percent_delay = get_closed_offset_delay(shutter) - _SEND_COMMAND_DELAY # delay between 99% (closed with blades open) and 100% (fully closed)
    else:
        first_percent_delay = one_percent_delay - _SEND_COMMAND_DELAY

    _send_command_from_thread(shutter, direction, thread_token)
    first_percent_delay = (first_percent_delay if first_percent_delay > 0 else 0) + _START_MOVING_DELAY
    if _shutter_thread_tokens[shutter] == thread_token:
        logs.debug('Sleep: {}s ({}% -> {}%)'.format(round(first_percent_delay, 3), current_state, current_state + increment))
    time.sleep(first_percent_delay)

    while True:
        current_state += increment
        _update_state_percent_from_thread(shutter, current_state, thread_token)
        if current_state == desired_state_percent:
            break
        if (current_state == 100 and increment == -1) or (current_state == 99 and increment == 1):
            if _shutter_thread_tokens[shutter] == thread_token:
                logs.debug('Sleep: {}s ({}% -> {}%)'.format(round(get_closed_offset_delay(shutter), 2), current_state, current_state + increment))
            time.sleep(get_closed_offset_delay(shutter)) # delay between 99% (closed with blades open) and 100% (fully closed)
        else:
            if _shutter_thread_tokens[shutter] == thread_token:
                logs.debug('Sleep: {}s ({}% -> {}%)'.format(round(one_percent_delay, 3), current_state, current_state + increment))
            time.sleep(one_percent_delay)

    if _shutter_thread_tokens[shutter] == thread_token:
        logs.debug('Reached target state for {}: {}%'.format(shutter, desired_state_percent))

    if current_state > 0 and current_state < 100:
        _send_command_from_thread(shutter, ShutterState.STOP, thread_token)

def operate(shutter: str, state: ShutterState, target_half_state = None) -> bool:
    '''
    Operate a shutter
    shutter: Name of shutter to operate
    state: Desired shutter state
    target_half_state: (Optional) Override height for HALF state from 0 (open) to 100 (closed)
    returns TRUE if successful
    '''
    shutter = shutter.lower()
    if not shutter in _shutters:
        raise ValueError('Unknown shutter: ' + str(shutter))

    if state == ShutterState.AUTO:
        raise ValueError('State "AUTO" is supported through shutters_auto.operate()')

    with _shutter_locks[shutter]:
        # Update token, which will cancel any ongoing operation
        thread_token = round(time.time() * 1000)
        if _shutter_thread_tokens.get(shutter, 0) == thread_token:
            thread_token -= 1;
        _shutter_thread_tokens[shutter] = thread_token

        # Fine-tunable shutter: movable to any desired height
        if shutter in _shutter_delay_close \
           and shutter in _shutter_closed_offset \
           and shutter in _shutter_delay_open \
           and shutter in _shutter_halfway:
            desired_state_percent = target_half_state
            if state == ShutterState.HALF and target_half_state is None:
                desired_state_percent = get_halfway_percent(shutter)
            if state == ShutterState.OPEN:
                desired_state_percent = 0
            if state == ShutterState.CLOSE:
                desired_state_percent = 100
            if state == ShutterState.STOP:
                _send_command(shutter, state)
                logs.info('Stopping shutter {} ({}%)'.format(shutter, get_current_state_percent(shutter)))
            else:
                t = Thread(target=_move_to_state_percent, args=[shutter, desired_state_percent, thread_token], name='Shutter operation')
                t.start()

        # Basic shutter management: only open/close
        else:
            if state == ShutterState.HALF:
                logs.error('Cannot set {} to HALF: No length/offset in config'.format(shutter))
                return False
            else:
                _send_command(shutter, state)
                if state == ShutterState.OPEN:
                    _shutter_state_percent[shutter] = 0
                elif state == ShutterState.CLOSE:
                    _shutter_state_percent[shutter] = 100
                else:
                    _shutter_state_percent[shutter] = None
                datastore.set(_SHUTTER_STATE_DATASTORE, _shutter_state_percent)

    return True
