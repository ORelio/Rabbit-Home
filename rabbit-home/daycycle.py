#!/usr/bin/env python3

# ====================================================================
# daycycle - compute day cycle to determine sunrise, sunset and season
# By ORelio (c) 2023-2025 - CDDL 1.0
# Uses https://github.com/skyfielders/python-skyfield
# ====================================================================

from threading import Thread, Lock
from typing import Callable
from configparser import ConfigParser
from datetime import datetime
from enum import Enum

import skyfield
import skyfield.almanac
import skyfield.api
import pytz
import tzlocal
import time

from events import EventHandler
from logs import logs

class DaycycleState(Enum):
    MORNING = 1
    LATE_MORNING = 2
    AFTERNOON = 3
    LATE_AFTERNOON = 4
    EVENING = 5
    NIGHT = 6

class Season(Enum):
    WINTER = 1
    SPRING = 2
    SUMMER = 3
    AUTUMN = 4

_sunrise_sunset_valid_phases = [
    'Day',
    'Civil twilight',
    'Nautical twilight',
    'Astronomical twilight'
]

_refresh_lock = Lock()
_eph_data = skyfield.api.load('de421.bsp')

# Location
_latitude = 0.0
_longitude = 0.0

# Calculation settings
_sunrise_sunset_phase = 'Day'
_sunrise_sunset_offset = 0.5
_late_morning_offset = 0.3
_noon_offset = 0.5
_late_afternoon_offset = 0.7
_evening_offset = 0.9

# Current time values
_last_calculation_date = None
_sunrise = None
_late_morning = None
_noon = None
_late_afternoon = None
_evening = None
_sunset = None

config = ConfigParser(interpolation=None)
config.read('config/daycycle.ini')

def _adjust_percentage(percentage: int) -> int:
    '''
    Make sure the supplied value is between 0 (inclusive) and 100 (exclusive)
    '''
    if percentage < 0:
        logs.warning('Found percentage "{}" > 0, adjusting to 0'.format(percentage))
        return 0
    if percentage > 99:
        logs.warning('Found percentage "{}" > 99, adjusting to 99'.format(percentage))
        return 99
    return percentage

options = config.options('Location')
if 'latitude' in options:
    _latitude = float(config.get('Location', 'latitude'))
if 'longitude' in options:
    _longitude = float(config.get('Location', 'longitude'))
options = config.options('Settings')
if 'sunrise_sunset' in options:
    _sunrise_sunset_phase = config.get('Settings', 'sunrise_sunset')
    if '+' in _sunrise_sunset_phase and '%' in _sunrise_sunset_phase:
        try:
            _sunrise_sunset_offset = _adjust_percentage(int(_sunrise_sunset_phase.split('+')[1].strip('%').strip()))
        except ValueError:
            _sunrise_sunset_offset = 0
        _sunrise_sunset_phase = _sunrise_sunset_phase.split('+')[0].strip()
    else:
        _sunrise_sunset_phase = config.get('Settings', 'sunrise_sunset')
    if not _sunrise_sunset_phase in _sunrise_sunset_valid_phases:
        _sunrise_sunset_phase = 'Day'
    if _sunrise_sunset_phase == _sunrise_sunset_valid_phases[-1]:
        _sunrise_sunset_offset = 0
    _late_morning_offset = _adjust_percentage(config.getint('Settings', 'late_morning', fallback=30))
    _noon_offset = _adjust_percentage(config.getint('Settings', 'noon', fallback=50))
    _late_afternoon_offset = _adjust_percentage(config.getint('Settings', 'late_afternoon', fallback=70))
    _evening_offset = _adjust_percentage(config.getint('Settings', 'evening', fallback=90))
    if _late_afternoon_offset >= _evening_offset:
        raise ValueError('"late_afternoon" must be lower than "evening"')
    if _noon_offset >= _late_afternoon_offset:
        raise ValueError('"noon" must be lower than "late_afternoon"')
    if _late_morning_offset >= _noon_offset:
        raise ValueError('"late_morning" must be lower than "noon"')
    logs.debug('Starting with lat={}, long={}, Phase={}, Offset={}%'.format(
        _latitude,
        _longitude,
        _sunrise_sunset_phase,
        _sunrise_sunset_offset
    ))
    logs.debug('Intermediate phases: LateMorning={}%, Noon={}%, LateAfternoon={}%, Evening={}%'.format(
        _late_morning_offset,
        _noon_offset,
        _late_afternoon_offset,
        _evening_offset
    ))
    _sunrise_sunset_offset = _sunrise_sunset_offset / 100
    _late_morning_offset = _late_morning_offset / 100
    _noon_offset = _noon_offset / 100
    _late_afternoon_offset = _late_afternoon_offset / 100
    _evening_offset = _evening_offset / 100

def _calculate_day_start_end_for_phase(sunrise_sunset_phase) -> (datetime, datetime):
    '''
    Calculate date of sunrise and sunset
    Based on https://rhodesmill.org/skyfield/examples.html#dark-twilight-day-example
    Uses latitude, longitude and sunrise/sunset phase from configuration
    '''
    timezone = tzlocal.get_localzone()
    date_now = datetime.now(tz=timezone)
    _day_begin = date_now.replace(hour=0, minute=0, second=0, microsecond=0)
    _day_end = date_now.replace(hour=23, minute=59, second=59, microsecond=999999)
    timescale = skyfield.api.load.timescale()
    t_start = timescale.from_datetime(_day_begin)
    t_end = timescale.from_datetime(_day_end)
    bluffton = skyfield.api.wgs84.latlon(_latitude, _longitude)
    time_function = skyfield.almanac.dark_twilight_day(_eph_data, bluffton)
    times, events = skyfield.almanac.find_discrete(t_start, t_end, time_function)
    # = Debug - print everything to the console =
    #previous_e = time_function(t_start).item()
    #for t, e in zip(times, events):
    #    tstr = str(t.astimezone(timezone))[:16]
    #    if previous_e < e:
    #        logs.debug(''.join([tstr, ' ', skyfield.almanac.TWILIGHTS[e], 'starts']))
    #    else:
    #        logs.debug(''.join([tstr, ' ', skyfield.almanac.TWILIGHTS[previous_e], 'ends']))
    #    previous_e = e
    # = Retrieve times of civil twilight
    #times = [datetime, datetime, datetime, datetime, datetime]
    #events = [type_int, type_int, type_int, type_int, type_int] / [1 2 3 4 3 2 1 0]
    #To get sunrise and sunset, we must first detemine event indices, then take times at same indices
    #Then we get indice corresponding to start of twilight for day and start of twilight for night
    #We keep (start of twilight) for sunrise and (start of twilight + 1 = end of twilight) for sunset
    twilights = skyfield.almanac.TWILIGHTS
    twilight_phase_enum_id = list(twilights.keys())[list(twilights.values()).index(sunrise_sunset_phase)] # Civil Twilight = 3
    twilight_phase_start_indexes = [i for i, e in enumerate(events) if e == twilight_phase_enum_id] # Civil Twilight gives [2, 4] / Day gives [3]
    if len(twilight_phase_start_indexes) == 1: # Day is middle phase, use it for both start and end. End+1 gives begin of twilight, i.e. sunset
        twilight_phase_start_indexes.append(twilight_phase_start_indexes[0])
    return times[twilight_phase_start_indexes[0]].astimezone(timezone), times[twilight_phase_start_indexes[1] + 1].astimezone(timezone)

def _calculate_day_start_end() -> (datetime, datetime):
    '''
    Calculate date of sunrise and sunset, optionally computing an offset between two phases
    '''
    if _sunrise_sunset_offset <= 0 or _sunrise_sunset_offset >= 0.999:
        return _calculate_day_start_end_for_phase(_sunrise_sunset_phase)
    sunrise_second, sunset_first = _calculate_day_start_end_for_phase(_sunrise_sunset_phase)
    sunrise_first, sunset_second = _calculate_day_start_end_for_phase(_sunrise_sunset_valid_phases[_sunrise_sunset_valid_phases.index(_sunrise_sunset_phase) + 1])
    sunrise = sunrise_first + (sunrise_second - sunrise_first) * (1.00 - _sunrise_sunset_offset)
    sunset = sunset_first + (sunset_second - sunset_first) * _sunrise_sunset_offset
    return sunrise, sunset

def _calculate_current_season() -> Season:
    '''
    Calculate current season based on current datetime and coordinates
    '''
    timezone = tzlocal.get_localzone()
    date_now = datetime.now(tz=timezone)
    year_begin = date_now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    year_end = date_now.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
    timescale = skyfield.api.load.timescale()
    t_start = timescale.from_datetime(year_begin)
    t_end = timescale.from_datetime(year_end)
    t, y = skyfield.almanac.find_discrete(t_start, t_end, skyfield.almanac.seasons(_eph_data))
    time_equinox_march = t[0].astimezone(timezone)
    time_solstice_june = t[1].astimezone(timezone)
    time_equinox_september = t[2].astimezone(timezone)
    time_solstice_december = t[3].astimezone(timezone)
    southern_emisphere = _latitude < 0
    if date_now < time_equinox_march:
        return Season.SUMMER if southern_emisphere else Season.WINTER
    elif date_now < time_solstice_june:
        return Season.AUTUMN if southern_emisphere else Season.SPRING
    elif date_now < time_equinox_september:
        return Season.WINTER if southern_emisphere else Season.SUMMER
    elif date_now < time_solstice_december:
        return Season.SPRING if southern_emisphere else Season.AUTUMN
    else:
        return Season.SUMMER if southern_emisphere else Season.WINTER

def _refresh_calculations():
    '''
    Refresh internal sunrise and sunset time
    Computation is expensive, so the result is cached
    '''
    global _last_calculation_date
    global _sunrise
    global _late_morning
    global _noon
    global _late_afternoon
    global _evening
    global _sunset
    global _season
    with _refresh_lock:
        current_date = datetime.now().strftime('%Y-%m-%d')
        if current_date != _last_calculation_date:
            _last_calculation_date = current_date
            _sunrise, _sunset = _calculate_day_start_end()
            _late_morning = _sunrise + (_sunset - _sunrise) * _late_morning_offset
            _noon = _sunrise + (_sunset - _sunrise) * _noon_offset
            _late_afternoon = _sunrise + (_sunset - _sunrise) * _late_afternoon_offset
            _evening = _sunrise + (_sunset - _sunrise) * _evening_offset
            _season = _calculate_current_season()
            logs.info('Computed sunrise: ' + str(_sunrise))
            logs.info('Computed late morning: ' + str(_late_morning))
            logs.info('Computed noon: ' + str(_noon))
            logs.info('Computed late afternoon: ' + str(_late_afternoon))
            logs.info('Computed evening: ' + str(_evening))
            logs.info('Computed sunset: ' + str(_sunset))
            logs.info('Computed season: ' + _season.name)

def get_datetime_now() -> datetime:
    '''
    Get current datetime in local timezone
    '''
    timezone = tzlocal.get_localzone()
    return datetime.now(tz=timezone)

def get_sunrise() -> datetime:
    '''
    Get sunrise datetime for today
    '''
    _refresh_calculations()
    return _sunrise

def get_late_morning() -> datetime:
    '''
    Get late morning datetime for today
    '''
    _refresh_calculations()
    return _late_morning

def get_noon() -> datetime:
    '''
    Get noon datetime for today
    '''
    _refresh_calculations()
    return _noon

def get_late_afternoon() -> datetime:
    '''
    Get late afternoon datetime for today
    '''
    _refresh_calculations()
    return _late_afternoon

def get_evening() -> datetime:
    '''
    Get evening datetime for today
    '''
    _refresh_calculations()
    return _evening

def get_sunset() -> datetime:
    '''
    Get sunset datetime for today
    '''
    _refresh_calculations()
    return _sunset

def is_day(date_time=None) -> bool:
    '''
    Determine if current (or provided) time is during day
    Note: provided time must be today.
    '''
    if date_time is None:
        date_time = get_datetime_now()
    return date_time >= get_sunrise() and date_time <= get_sunset()

def is_night(date_time=None) -> bool:
    '''
    Determine if current (or provided) time is during night.
    Note: provided time must be today.
    '''
    return not is_day(date_time)

def get_state(date_time=None) -> DaycycleState:
    '''
    Determine daycycle state for current (or provided) time.
    Note: provided time must be today.
    '''
    if date_time is None:
        date_time = get_datetime_now()
    sunrise = get_sunrise()
    late_morning = get_late_morning()
    noon = get_noon()
    late_afternoon = get_late_afternoon()
    evening = get_evening()
    sunset = get_sunset()
    if date_time >= sunrise and date_time < late_morning:
        return DaycycleState.MORNING
    if date_time >= late_morning and date_time < noon:
        return DaycycleState.LATE_MORNING
    if date_time >= noon and date_time < late_afternoon:
        return DaycycleState.AFTERNOON
    if date_time >= late_afternoon and date_time < evening:
        return DaycycleState.LATE_AFTERNOON
    if date_time >= evening and date_time < sunset:
        return DaycycleState.EVENING
    return DaycycleState.NIGHT

def get_season() -> Season:
    '''
    Get current season
    '''
    return _season

'''
Daycycle Event Handler
Callbacks will receive args = DaycycleState
'''
event_handler = EventHandler('Daycycle')

def _event_thread():
    '''
    Monitor daylight and run callbacks
    '''
    previous_state = get_state()
    while True:
        time.sleep(30)
        current_state = get_state()
        if current_state != previous_state:
            previous_state = current_state
            _refresh_calculations()
            event_handler.dispatch(current_state)

_refresh_calculations()
_event_thread_instance = Thread(target=_event_thread, name='Daycycle event dispatcher')
_event_thread_instance.start()
