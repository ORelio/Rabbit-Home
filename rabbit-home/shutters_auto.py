#!/usr/bin/env python3

# ==========================================================================================
# shutters_auto - automatically adjust shutters depending on time of day, season and weather
# By ORelio (c) 2023-2024 - CDDL 1.0
# ==========================================================================================

from configparser import ConfigParser
from threading import Thread, Lock

from shutters import ShutterState
from daycycle import DaycycleState, Season
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

# == Shutter presets parsing and handling ==

class ShutterPreset:
    '''
    Represents a shutter preset mapping shutter state to specific conditions
    '''
    # Settings
    state: ShutterState
    percent: int

    # Conditions
    dayphase: DaycycleState
    season: Season
    temp: TemperatureEventType

    def __init__(self, config_key: str, config_val: str):
        '''
        Initialize a new shutter preset based on config file entry
        '''
        if not config_key.lower().startswith('state'):
            raise ValueError('Invalid config key for ShutterPreset: {}'.format(config_key))

        # Determine desired state
        state = None
        percent = None
        if config_val.endswith('%'):
            state = ShutterState.HALF
            percent = int(config_val.strip('%'))
            if percent <= 0:
                state = ShutterState.OPEN
                percent = None
            if percent >= 100:
                state = ShutterState.CLOSE
                percent = None
        else:
            state = ShutterState[config_val.upper()]
            if state == ShutterState.AUTO:
                raise ValueError('Cannot use state AUTO in shutter preset')

        # Determine conditions
        dayphase = None
        season = None
        temp = None
        for condition in config_key.split('.'):
            condition = condition.upper()
            if condition == 'STATE':
                pass
            elif condition in [item.name for item in DaycycleState]:
                dayphase = DaycycleState[condition]
            elif condition in [item.name for item in Season]:
                season = Season[condition]
            elif condition in [item.name for item in TemperatureEventType] and condition != 'DATA':
                temp = TemperatureEventType[condition]
            else:
                raise ValueError('Unknown shutter preset condition: {}'.format(condition))

        # Initialize preset data
        self.state = state
        self.percent = percent
        self.dayphase = dayphase
        self.season = season
        self.temp = temp

    def __str__(self) -> str:
        '''
        String representation of the preset
        '''
        return 'ShutterPreset(state={}, percent={}, dayphase={}, season={}, temp={})'.format(
            self.state.name if self.state else None,
            self.percent,
            self.dayphase.name if self.dayphase else None,
            self.season.name if self.season else None,
            self.temp.name if self.temp else None
        )

    def matches(self, dayphase: DaycycleState, season: Season, temp: TemperatureEventType):
        '''
        Check if the preset matches the specified conditions, unset condition being catch-all
        '''
        return (not self.dayphase or self.dayphase == dayphase) \
           and (not self.season or self.season == season) \
           and (not self.temp or self.temp == temp)

    def weight(self) -> int:
        '''
        Amount of criteria in the preset
        '''
        w = 0
        if self.dayphase:
            w += 1
        if self.season:
            w += 1
        if self.temp:
            w += 1
        return w

    def __lt__(self, other) -> bool:
        '''
        Sort presets by weight then priority
        '''
        # more criteria > less criteria
        if self.weight() < other.weight():
            return True
        if self.weight() > other.weight():
            return False

        # temperature > season > dayphase
        if not self.temp and other.temp:
            return True
        if self.temp and not other.temp:
            return False
        if not self.season and other.season:
            return True
        if self.season and not other.season:
            return False
        if not self.dayphase and other.dayphase:
            return True
        if self.dayphase and not other.dayphase:
            return False

        # Seems like both are equal, should not happen unless configuration file had ambiguous entries
        raise ValueError('Priority conflict between {} and {}'.format(self, other))

    def find_most_appropriate(presets: list, dayphase: DaycycleState, season: Season, temp: TemperatureEventType) -> 'ShutterPreset':
        '''
        For the specified list of presets, find the one matching the specified conditions most closely.
        '''
        if len(presets) > 0:
            matching = [item for item in presets if item.matches(dayphase, season, temp)]
            matching.sort(reverse=True)
            return matching[0]
        return None

# == Load configuration ==

_shutter_to_rabbit = dict()
_shutter_to_presets = dict()

_defective_shutter = dict()
_defective_shutter_lock = dict()
_defective_shutter_token = dict()

config = ConfigParser(interpolation=None)
config.read('config/shutters_auto.ini')
for section in config.sections():
    shutter = config.get(section, 'shutter').lower()
    opening = openings.get_opening_from_shutter(shutter)
    if opening:
        _shutter_to_rabbit[shutter] = rabbits.get_name(openings.get_rabbit_from_opening(opening))
    else:
        _shutter_to_rabbit[shutter] = None
        logs.warning('Missing rabbit for shutter: {}. Set mappings in config/openings.ini')
    if shutter in _shutter_to_presets:
        raise ValueError('Duplicate shutter "{}"'.format(shutter))
    _shutter_to_presets[shutter] = list()
    logs.debug('Loading presets for "{}":'.format(shutter))
    for (key, val) in config.items(section):
        if key.lower().startswith('state'):
            preset = ShutterPreset(key, val)
            logs.debug('[{}/{}] {}'.format(shutter, key, preset))
            _shutter_to_presets[shutter].append(preset)
    _defective_shutter[shutter] = config.getboolean(section, 'defective', fallback=False)
    if _defective_shutter[shutter]:
        _defective_shutter_lock[shutter] = Lock()
        _defective_shutter_token[shutter] = 0
logs.debug('Loaded {} shutters: {}'.format(
    len(_shutter_to_presets), ', '.join(list(_shutter_to_presets.keys()))))

# == API and event handlers ==

def _can_operate(current_rabbit: str, desired_rabbit: str, override_sleep) -> bool:
    '''
    Check if automatic operation is allowed for a specific rabbit (tied to a specific room)
    current_rabbit: Rabbit (room) we want to operate, or None if we want to operate all rabbits (rooms)
    desired_rabbit: Rabbit (room) for the current set of shutters
    override_sleep: Allow operation EVEN IF the rabbit is sleeping
    Returns TRUE if we can operate the current set of shutters
    '''
    return ((current_rabbit is None or current_rabbit.lower() == desired_rabbit.lower()) and (override_sleep or not nabstate.is_sleeping(desired_rabbit)))

def adjust_shutters(current_rabbit: str = None, shutter_name: str = None, override_sleep: bool = False, state: ShutterState = ShutterState.AUTO):
    '''
    Reset shutter position for all rooms, or only for a specific rabbit (tied to a specific room)
    Default shutter position depends on time of day
    current_rabbit: Limit operation to the specified rabbit
    shutter_name: Limit operation to the specified shutter
    override_sleep: Allow operation EVEN IF the rabbits are sleeping
    state: Set desired state instead of auto-determining appropriate state
    '''
    if current_rabbit:
        current_rabbit = rabbits.get_name(current_rabbit)
    for shutter in _shutter_to_presets:
        if shutter_name is None or shutter == shutter_name:
            if ((current_rabbit is None or current_rabbit == _shutter_to_rabbit[shutter]) \
              and (override_sleep or not nabstate.is_sleeping(_shutter_to_rabbit[shutter]))) \
              and openings.get_current_state(shutter=shutter) != OpenState.OPEN:
                operate(shutter, state)

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
        for shutter in _shutter_to_presets:
            success = success and operate(shutter, state, target_half_state)
        return success

    # Auto determine state using presets?
    if state == ShutterState.AUTO:
        dayphase = daycycle.get_state()
        season = daycycle.get_season()
        temp_state = temperature.get_state_outside()
        preset = ShutterPreset.find_most_appropriate(_shutter_to_presets[shutter], dayphase=dayphase, season=season, temp=temp_state)
        logs.info('Auto-Selected state for shutter={}, dayphase={}, season={}, temperature={}: {}'.format(shutter, dayphase.name, season.name, temp_state.name, preset))
        if preset is None:
            return False
        state = preset.state
        target_half_state = preset.percent

    # Operate a shutter that may block itself askew?
    if _defective_shutter[shutter]:
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
