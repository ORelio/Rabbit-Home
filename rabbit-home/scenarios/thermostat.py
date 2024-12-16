#!/usr/bin/env python3

# ==================================================================================
# Thermostat Scenario - Automatically turn heater ON or OFF depending on temperature
# By ORelio (c) 2024 - CDDL 1.0
# ==================================================================================

from scenarios import Event, subscribe, unsubscribe
from temperature import TemperatureEventType
from logs import logs

import plugs433
import temperature

thermostat_on = False

def init():
    subscribe(Event.TEMPERATURE, run)
    subscribe(Event.TEMPERATURE_DATA, run)

def run(event: Event, rabbit: str = None, args: dict = {}):
    global thermostat_on
    if 'rabbit' in args and args['rabbit'] == 'rabbitone':

        if event == Event.TEMPERATURE_DATA:
            # Convert data events into temperature events to resend heater commands
            event = Event.TEMPERATURE
            args['type'] = temperature.get_state(rabbit='rabbitone')

        if event == Event.TEMPERATURE:
            if args['type'] == TemperatureEventType.COLD:
                if not thermostat_on:
                    logs.info('COLD: Turning ON heater')
                plugs433.switch('heater', True)
                thermostat_on = True
            else:
                if thermostat_on:
                    logs.info('NORMAL: Turning OFF heater')
                plugs433.switch('heater', False)
                thermostat_on = False
