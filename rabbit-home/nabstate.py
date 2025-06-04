#!/usr/bin/env python3

# ===================================================================================
# nabstate - remotely monitor and change the sleep/awake state (Nabaztag/tag:tag:tag)
# Monitoring state works using nabd, changing state is done using nabweb
# By ORelio (c) 2023-2025 - CDDL 1.0
# ===================================================================================

from flask import Blueprint, request
from threading import Thread, Lock
from typing import Callable

import time

import rabbits
import nabweb
import nabd

from events import EventHandler
from logs import logs

_state_lock = Lock()
_stateinfo = dict()
_sleeping = dict()
_last_automated_state_change = dict()

STATE_IDLE = 'idle'
STATE_ASLEEP = 'asleep'
STATE_FALLING_ASLEEP = 'falling_asleep'
STATE_WAKING_UP = 'waking_up'
STATE_OFFLINE = 'offline'

'''
Nabstate Event Handler
Callbacks will receive args = rabbit: str,  new_state: str, automated: bool
Automated means that we just programmatically changed the rabbit state
'''
event_handler = EventHandler('Nabstate', log_level=None)

def get_state(rabbit: str):
    '''
    Get current Nabaztag state
    '''
    nabaztag_ip = rabbits.get_ip(rabbit)
    with _state_lock:
        return _stateinfo.get(nabaztag_ip, STATE_OFFLINE)

def _nabd_state_monitor(rabbit: str, nabd_event: dict):
    '''
    Internal. Callback for monitoring nabd events
    '''
    nabaztag_ip = rabbits.get_ip(rabbit)
    if 'type' in nabd_event and nabd_event['type'] == 'state' and 'state' in nabd_event:
        _cache_current_state(nabaztag_ip, nabd_event['state'])
        _handle_sleep_wakeup_event(nabaztag_ip, nabd_event['state'])
        event_handler.dispatch(rabbits.get_name(nabaztag_ip), nabd_event['state'], False)

def _cache_current_state(rabbit: str, state: str):
    '''
    Internal. Take note of new Nabaztag state
    '''
    nabaztag_ip = rabbits.get_ip(rabbit)
    with _state_lock:
        _stateinfo[nabaztag_ip] = state

def _handle_sleep_wakeup_event(rabbit: str, state: str):
    '''
    Internal. Detect transition between sleep <=> awake state and generate a specific event
    '''
    nabaztag_ip = rabbits.get_ip(rabbit)
    logs.info('New state for ' + rabbits.get_name(rabbit) + ': ' + state)
    if state == STATE_ASLEEP or state == STATE_IDLE:
        new_sleep_state = (state == STATE_ASLEEP)
        old_sleep_state = new_sleep_state
        with _state_lock:
            if nabaztag_ip in _sleeping:
                old_sleep_state = _sleeping[nabaztag_ip]
            _sleeping[nabaztag_ip] = new_sleep_state
        if new_sleep_state != old_sleep_state:
            event = STATE_FALLING_ASLEEP if new_sleep_state else STATE_WAKING_UP
            event_was_automated = False
            with _state_lock:
                if _last_automated_state_change.get(nabaztag_ip, 0) + 60 > time.time():
                    event_was_automated = True
                    _last_automated_state_change[nabaztag_ip] = 0
            event_handler.dispatch(rabbits.get_name(nabaztag_ip), event, event_was_automated)

def initialize(rabbit: str):
    '''
    Start monitoring Nabaztag state in a background thread
    '''
    nabaztag_ip = rabbits.get_ip(rabbit)
    nabd.event_handler.subscribe(_nabd_state_monitor)
    nabd.connect(nabaztag_ip)

def set_sleeping(rabbit: str, sleeping: bool, play_sound: bool = False):
    '''
    Set Nabaztag sleeping state
    rabbit: Rabbit to set sleeping or None for all rabbits
    sleeping: True to set asleep, False to set awake
    play_sound: True to play sleep/wakeup sound
    '''
    if rabbit is None:
        for rabbit in rabbits.get_all():
            set_sleeping(rabbit, sleeping=sleeping, play_sound=play_sound)
        return

    nabaztag_ip = rabbits.get_ip(rabbit)

    # Change state only if current state is not the desired state
    current_state = get_state(nabaztag_ip)
    if current_state == STATE_OFFLINE:
        return # Cannot change state
    if current_state == STATE_ASLEEP and sleeping:
        return # Already sleeping
    if current_state != STATE_ASLEEP and not sleeping:
        return # Already awake (idle or doing something else)

    # Adjust settings
    nabweb.change_settings(nabaztag_ip, nabweb.API_NABCLOCKD, {
        'play_wakeup_sleep_sounds': str(play_sound).lower(),
        'settings_per_day': 'false',
    })

    # Change setting to cancel manual wakeup - pressing nabaztag button to wake it up
    nabweb.change_settings(nabaztag_ip, nabweb.API_NABCLOCKD, {
        'sleep_time': '00:00',
        'wakeup_time': '00:00',
    })

    # Set sleep time so that nabaztag will be always awake or always sleeping
    nabweb.change_settings(nabaztag_ip, nabweb.API_NABCLOCKD, {
        'sleep_time': '00:00' if sleeping else '99:99',
        'wakeup_time': '99:99' if sleeping else '00:00',
    })

    # Take note that we just programmatically changed the rabbit's state
    with _state_lock:
        _last_automated_state_change[nabaztag_ip] = time.time()

    # The sleep_wakeup_event will occur after a delay (a few seconds)
    # If we successfully woke up a rabbit, we want to make it appear awake
    # immediately as some scenarios will not occur if is_sleeping() returns True
    if not sleeping:
        _cache_current_state(rabbit, STATE_IDLE)

def any_sleeping() -> bool:
    '''
    Check if at least one rabbit is currently asleep
    '''
    for rabbit in rabbits.get_all():
        if get_state(rabbit) == STATE_ASLEEP or get_state(rabbit) == STATE_OFFLINE:
            return True
    return False

def is_sleeping(rabbit: str) -> bool:
    '''
    Check if the specified rabbit is currently sleeping
    '''
    return get_state(rabbit) == STATE_ASLEEP or get_state(rabbit) == STATE_OFFLINE

'''
State API for webhook clients
'''
nabstate_api = Blueprint('nabstate_api', __name__)

@nabstate_api.route('/api/v1/nabstate/change')
def nabstate_api_webhook():
    '''
    API for changing nabaztag sleep state
    '''
    rabbit = request.args.get('rabbit')
    sleep = str(request.args.get('sleep')).lower().strip() in ['1', 'true']
    sounds = str(request.args.get('sounds')).lower().strip() in ['1', 'true']
    logs.info('Nabstate API call: rabbit={}, sleep={}, sounds={}'.format(rabbit, sleep, sounds))

    # Custom argument: Specify Nabaztag IP
    if rabbit and not rabbits.is_rabbit(rabbit):
        return 'Invalid request', 400

    # No rabbit set but request comes from a rabbit: set caller as target
    if rabbit is None and rabbits.is_rabbit(request.remote_addr):
        rabbit = request.remote_addr

    process_t = Thread(target=set_sleeping, args=[rabbit, sleep, sounds], name='Nabstate API')
    process_t.start()

    return 'OK', 200

# Initialize nabstate on first module import
for rabbit in rabbits.get_all():
    logs.debug('Initializing: ' + rabbit)
    initialize(rabbit)
