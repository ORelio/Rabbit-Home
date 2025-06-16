#!/usr/bin/env python3

# =========================================================
# Away mode - Put rabbits to sleep while away using a ztamp
# By ORelio (c) 2023-2025 - CDDL 1.0
# =========================================================

from scenarios import Event, subscribe, unsubscribe
from shutters import ShutterState
from openings import OpenState
from logs import logs

import time

import datastore
import rabbits
import nabstate
import shutters_auto

AWAY_DATASTORE_KEY = 'scenario.away'
away = datastore.get(AWAY_DATASTORE_KEY, False)
away_time = 0

def init():
    subscribe(Event.WAKEUP, wakeup)
    subscribe(Event.OPEN_CLOSE, door)
    if away:
        _away(True)

# RFID, Switch or API: Switch Away mode
def run(event: Event, rabbit: str = None, args: dict = {}):
    logs.info('Away: Event={}, Rabbit={}, Args={}'.format(event, rabbits.get_name(rabbit), args))
    if 'away' in args and args['away'] == False:
        _back(True)
    else:
        _away(False)

# Button on rabbit: End Away mode
def wakeup(event: Event, rabbit: str = None, args: dict = {}):
    if not 'automated' in args or not args['automated']:
        logs.info('Wakeup: ' + str(rabbits.get_name(rabbit)))
        _back(False)

# Open front door: End Away mode
def door(event: Event, rabbit: str = None, args: dict = {}):
    if 'is_front_door' in args and args['is_front_door'] \
      and 'state' in args and args['state'] == OpenState.OPEN:
        if away_time + 60 > time.time():
            logs.debug('Front door opened quickly after activating away mode, ignoring')
        else:
            logs.info('Front door opened')
            _back(False)

# Start Away mode
def _away(force: bool):
    global away
    global away_time
    if not away or force:
        if force:
            logs.info('Resuming Away mode')
            away_time = time.time() - 60
        else:
            logs.info('Entering Away mode')
            away = datastore.set(AWAY_DATASTORE_KEY, True)
            away_time = time.time()
        shutters_auto.operate('all', ShutterState.CLOSE)
        time.sleep(30) # Put rabbits to sleep after a delay
        if away: # In case away mode got cancelled quickly
            for rabbit in rabbits.get_all():
                nabstate.set_sleeping(rabbit, sleeping=True, play_sound=False)
    else:
        logs.info('Already in Away mode, nothing to do')

# End Away mode
def _back(force: bool):
    global away
    if away or force:
        logs.info('Exiting Away mode')
        away = datastore.set(AWAY_DATASTORE_KEY, False)
        # Open shutters without waiting for other rabbits to wake up
        shutters_auto.adjust_shutters(override_sleep=True)
        # Wake up all rabbits (slow, so doing it last)
        for rabbit in rabbits.get_all():
            nabstate.set_sleeping(rabbit, sleeping=False, play_sound=False)
    else:
        logs.info('Not in Away mode, nothing to do')
