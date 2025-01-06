#!/usr/bin/env python3

# ===============================================================================
# Auto Shutters Scenario - Automatically adjust shutters depending on time of day
# By ORelio (c) 2023-2024 - CDDL 1.0
# ===============================================================================

from scenarios import Event, subscribe, unsubscribe
from logs import logs

import shutters_auto

def init():
    subscribe(Event.SUNRISE, run)
    subscribe(Event.LATE_MORNING, run)
    subscribe(Event.NOON, run)
    subscribe(Event.LATE_AFTERNOON, run)
    subscribe(Event.EVENING, run)
    subscribe(Event.SUNSET, run)
    subscribe(Event.TEMPERATURE, run)
    subscribe(Event.OPEN_CLOSE, window)

def run(event: Event, rabbit: str = None, args: dict = {}):
    if event == Event.TEMPERATURE and not args['outside']:
        return
    logs.info('Readjusting shutters for event: ' + str(event))
    shutters_auto.adjust_shutters()

def window(event: Event, rabbit: str = None, args: dict = {}):
    if 'state' in args and 'shutter' in args:
        logs.info('Readjusting shutter for window open/close event: {}, {}'.format(args['shutter'], args['state'].name))
        shutters_auto.adjust_shutters(shutter_name=args['shutter'])
