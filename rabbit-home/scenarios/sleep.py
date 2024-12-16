#!/usr/bin/env python3

# ====================================================================
# Sleep mode - Close shutters and put rabbit(s) to sleep using a ztamp
# By ORelio (c) 2023-2024 - CDDL 1.0
# ====================================================================

from scenarios import Event, subscribe, unsubscribe
from shutters import ShutterState
from datetime import datetime
from daycycle import DaycycleState
from logs import logs

import rabbits
import nabstate
import shutters_auto
import daycycle
import nabweb

sleeping = dict()

def init():
    subscribe(Event.WAKEUP, wakeup)

# Sleep via RFID or API: Use Ztamp to put rabbit to sleep
def run(event: Event, rabbit: str = None, args: dict = {}):
    global sleeping
    if (event == Event.API or event == Event.RFID) and rabbit is not None:
        rabbit = rabbits.get_name(rabbit)
        logs.info('Sleep: {}'.format(rabbit))
        if daycycle.is_night():
            shutters_auto.operate('shutterone', ShutterState.CLOSE)
            shutters_auto.operate('shuttertwo', ShutterState.CLOSE)
        else:
            shutters_auto.operate('shuttertwo', ShutterState.CLOSE)
        sleeping[rabbit] = True
        nabstate.set_sleeping(rabbit, True, True)
    else:
        logs.error('Invalid arguments')

# Wakeup via button on rabbit
def wakeup(event: Event, rabbit: str = None, args: dict = {}):
    global sleeping
    if rabbit is not None:
        rabbit = rabbits.get_name(rabbit)
        if rabbit in sleeping:
            logs.info('Wakeup: ' + str(rabbit))
            del sleeping[rabbit]
            shutters_auto.adjust_shutters(rabbit)
            if daycycle.get_state() == DaycycleState.MORNING:
                nabweb.launch_weather(rabbit)
        else:
            logs.info('Ignoring Wakeup: ' + rabbit)
    else:
        logs.info('Ignoring Wakeup: ' + rabbit)
