#!/usr/bin/env python3

# =========================================================
# Away mode - Put rabbits to sleep while away using a ztamp
# By ORelio (c) 2023-2024 - CDDL 1.0
# =========================================================

from scenarios import Event, subscribe, unsubscribe
from shutters import ShutterState
from logs import logs

import rabbits
import nabstate
import shutters_auto

away = False

def init():
    subscribe(Event.WAKEUP, wakeup)

# RFID, Switch or API: Switch Away mode
def run(event: Event, rabbit: str = None, args: dict = {}):
    logs.info('Away: Event={}, Rabbit={}, Args={}'.format(event, rabbits.get_name(rabbit), args))
    if 'away' in args and args['away'] == False:
        _back(True)
    else:
        _away()

# Button on rabbit: End Away mode
def wakeup(event: Event, rabbit: str = None, args: dict = {}):
    logs.info('Wakeup: ' + str(rabbits.get_name(rabbit)))
    _back(False)

# Start Away mode
def _away():
    global away
    if not away:
        logs.info('Entering Away mode')
        away = True
        shutters_auto.operate('all', ShutterState.CLOSE)
        for rabbit in rabbits.get_all():
            nabstate.set_sleeping(rabbit, sleeping=True, play_sound=False)
    else:
        logs.info('Already in Away mode, nothing to do')

# End Away mode
def _back(force: bool):
    global away
    if away or force:
        logs.info('Exiting Away mode')
        away = False
        # Open shutters without waiting for other rabbits to wake up
        shutters_auto.adjust_shutters(override_sleep=True)
        # Wake up the other rabbits (slow, so doing it last)
        for rabbit in rabbits.get_all():
            nabstate.set_sleeping(rabbit, sleeping=False, play_sound=False)
    else:
        logs.info('Not in Away mode, nothing to do')
