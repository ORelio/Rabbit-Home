#!/usr/bin/env python3

# ======================================================================================
# shutters_auto - automatically adjust shutters depending on time of day and temperature
# By ORelio (c) 2023-2024 - CDDL 1.0
# ======================================================================================

from configparser import ConfigParser
from threading import Thread, Lock
from shutters import ShutterState
from daycycle import DaycycleState
from temperature import TemperatureEventType
from openings import OpenState
from logs import logs

import rabbits
import nabstate
import shutters
import openings
import daycycle
import temperature
import time

_shutter_to_rabbit = dict()
_shutter_to_state = dict()

_defective_shutter = dict()
_defective_shutter_lock = dict()
_defective_shutter_token = dict()

config = ConfigParser(interpolation=None)
config.read('config/shutters_auto.ini')
for section in config.sections():
    shutter = config.get(section, 'shutter').lower()
    opening = openings.get_opening_from_shutter(shutter)
    if opening:
        _shutter_to_rabbit[shutter] = openings.get_rabbit_from_opening(opening)
    else:
        _shutter_to_rabbit[shutter] = None
        logs.warning('Missing rabbit for shutter: {}. Set mappings in config/openings.ini')
    _shutter_to_state[shutter] = dict()
    for day_state in DaycycleState:
        _shutter_to_state[shutter][day_state] = dict()
        for temp_type in TemperatureEventType:
            if temp_type != TemperatureEventType.DATA:
                setting_key = 'state.{}.{}'.format(day_state.name.lower(), temp_type.name.lower())
                desired_state = config.get(section, setting_key)
                desired_percent = None
                if desired_state.endswith('%'):
                    desired_percent = int(desired_state.strip('%'))
                    desired_state = ShutterState.HALF
                    if desired_percent <= 0:
                        desired_state = ShutterState.OPEN
                        desired_percent = None
                    if desired_percent >= 100:
                        desired_state = ShutterState.CLOSE
                        desired_percent = None
                else:
                    desired_state = ShutterState[desired_state.upper()]
                _shutter_to_state[shutter][day_state][temp_type] = (desired_state, desired_percent)
    _defective_shutter[shutter] = config.getboolean(section, 'defective', fallback=False)
    if _defective_shutter[shutter]:
        _defective_shutter_lock[shutter] = Lock()
        _defective_shutter_token[shutter] = 0
logs.debug('Loaded {} shutters: {}'.format(
    len(_shutter_to_state), ', '.join(list(_shutter_to_state.keys()))))

def _can_operate(current_rabbit: str, desired_rabbit: str, override_sleep) -> bool:
    '''
    Check if automatic operation is allowed for a specific rabbit (tied to a specific room)
    current_rabbit: Rabbit (room) we want to operate, or None if we want to operate all rabbits (rooms)
    desired_rabbit: Rabbit (room) for the current set of shutters
    override_sleep: Allow operation EVEN IF the rabbit is sleeping
    Returns TRUE if we can operate the current set of shutters
    '''
    return ((current_rabbit is None or current_rabbit.lower() == desired_rabbit.lower()) and (override_sleep or not nabstate.is_sleeping(desired_rabbit)))

def adjust_shutters(current_rabbit: str = None, shutter_name: str = None, override_sleep: bool = False):
    '''
    Reset shutter position for all rooms, or only for a specific rabbit (tied to a specific room)
    Default shutter position depends on time of day
    current_rabbit: Limit operation to the specified rabbit
    shutter_name: Limit operation to the specified shutter
    override_sleep: Allow operation EVEN IF the rabbits are sleeping
    '''
    day_state = daycycle.get_state()
    temp_state = temperature.get_state_outside()
    if current_rabbit:
        current_rabbit = rabbits.get_name(current_rabbit)

    logs.info('Moving shutter{}: daycycle={}, temperature={}, rabbit={}'.format(
        ' {}'.format(shutter_name) if shutter_name else 's',
        day_state.name, temp_state.name, current_rabbit)
    )

    for shutter in _shutter_to_state:
        if shutter_name is None or shutter == shutter_name:
            if ((current_rabbit is None or current_rabbit == _shutter_to_rabbit[shutter]) \
              and (override_sleep or not nabstate.is_sleeping(_shutter_to_rabbit[shutter]))):
                state, percent = _shutter_to_state[shutter][day_state][temp_state]
                if openings.get_current_state(shutter=shutter) == OpenState.OPEN:
                    state = ShutterState.OPEN
                    percent = 0
                operate(shutter, state, target_half_state=percent)

def _operate_defective_from_thread(shutter: str, state: ShutterState, target_half_state: int, thread_token: int):
    '''
    Operate a defective shutter, acquiring lock and validating thread token
    shutter: Target shutter
    state: Desired shutter state
    target_half_state: Override height for HALF state from 0 (open) to 100 (closed)
    thread_token: Only send command if the current token matches the provided one
    '''
    if _defective_shutter_token[shutter] == thread_token:
        with _defective_shutter_lock[shutter]:
            return shutters.operate(shutter, state, target_half_state)

def _operate_defective(shutter: str, state: ShutterState, target_half_state: int, thread_token: int):
    '''
    Operate a shutter that often blocks itself askew when going down from fully OPEN state
    Work around this defect by doing small, repetitive forward-backward moves
    shutter: Target shutter
    state: Desired final shutter state
    target_half_state: Override height for HALF state from 0 (open) to 100 (closed)
    thread_token: Stop operating if another operation changes the token
    '''
    if target_half_state is None:
        if state == ShutterState.OPEN:
            target_half_state = 0
        if state == ShutterState.HALF:
            target_half_state = shutters._shutter_halfway[shutter]
        if state == ShutterState.CLOSE:
            target_half_state = 100

    # Check current state
    current_state = shutters.get_current_state_percent(shutter)

    # Handle problematic state: 0-30% or unknown state and need to move down
    if state in [ShutterState.CLOSE, ShutterState.HALF] and \
       (current_state is None or (current_state < 30 and current_state < target_half_state)):
        # Go to 0% first, going UP is safe, but going DOWN may block the shutter askew
        _operate_defective_from_thread(shutter, ShutterState.OPEN, None, thread_token)
        current_state = ShutterState.OPEN
        while shutters.get_current_state_percent(shutter) is None \
           or shutters.get_current_state_percent(shutter) > 0:
            time.sleep(0.1)
        # Procedure to go from 0 to 30% without blocking shutters
        for i in range(8):
            _operate_defective_from_thread(shutter, ShutterState.OPEN, None, thread_token)
            time.sleep(1.5)
            _operate_defective_from_thread(shutter, ShutterState.CLOSE, None, thread_token)
            time.sleep(2)
        # Use our token to stop ongoing operation and override the current height
        shutters._shutter_thread_tokens[shutter] = _defective_shutter_token[shutter]
        shutters._update_state_percent_from_thread(shutter, 30, _defective_shutter_token[shutter])

    # Safe state reached, operate normally
    _operate_defective_from_thread(shutter, state, target_half_state, thread_token)

def operate(shutter: str, state: ShutterState, target_half_state = None, direct_command = False) -> bool:
    '''
    Operate a shutter - with automatic special operation for defective shutters
    shutter: Name of shutter to operate or 'all' of all shutters
    state: Desired shutter state
    target_half_state: (Optional) Override height for HALF state from 0 (open) to 100 (closed)
    direct_command: (Optional) Direct command from switch, no need for defective shutter workaround
    returns TRUE if successful
    '''
    shutter = shutter.lower()

    # Operate all shutters at once?
    if shutter == 'all':
        success = True
        for shutter in _shutter_to_state:
            success = success and operate(shutter, state, target_half_state)
        return success

    # Operate a shutter that may block itself askew?
    elif _defective_shutter[shutter]:
        # Neutralize any running thread for defective shutter
        _defective_shutter_token[shutter] = round(time.time() * 1000)
        if direct_command:
            # Direct control by the user using wall switch
            if state == ShutterState.HALF:
                # Erase internal state to force relaunch procedure
                shutters.operate(shutter, ShutterState.STOP)
            return shutters.operate(shutter, state, target_half_state)
        else:
            if state == ShutterState.STOP:
                # No need for thread for simply stopping the shutter
                return shutters.operate(shutter, ShutterState.STOP)
            else:
                # Run dedicated thread to properly manage this delicate shutter
                Thread(target=_operate_defective, args=[shutter, state, target_half_state, _defective_shutter_token[shutter]], name='Defective shutter operation ({})'.format(shutter)).start()
                return True

    # Normal shutter operation
    else:
        return shutters.operate(shutter, state, target_half_state)
