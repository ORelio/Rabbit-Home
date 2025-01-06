#!/usr/bin/env python3

# ==================================================
# scenarios - manage scenarios and associated events
# By ORelio (c) 2023-2025 - CDDL 1.0
# ==================================================

import importlib
import sys
import os

from flask import Blueprint
from enum import Enum
from threading import Thread, Lock
from typing import Callable

import nabstate
import daycycle
import rabbits
import pcstate
import temperature
import openings

from events import EventHandler
from daycycle import DaycycleState
from pcstate import PcState
from temperature import TemperatureEvent, TemperatureEventType
from openings import OpenState
from logs import logs

class Event(Enum):
    API = 1
    RFID = 2
    SWITCH = 3
    SLEEP = 4
    WAKEUP = 5
    SUNRISE = 6
    LATE_MORNING = 7
    NOON = 8
    LATE_AFTERNOON = 9
    EVENING = 10
    SUNSET = 11
    TEMPERATURE = 12
    TEMPERATURE_DATA = 13
    OPEN_CLOSE = 14
    PC_STATE = 15

_nabstate_to_event = {
    nabstate.STATE_FALLING_ASLEEP: Event.SLEEP,
    nabstate.STATE_WAKING_UP: Event.WAKEUP
}

_daycycle_to_event = {
    DaycycleState.MORNING: Event.SUNRISE,
    DaycycleState.LATE_MORNING: Event.LATE_MORNING,
    DaycycleState.AFTERNOON: Event.NOON,
    DaycycleState.LATE_AFTERNOON: Event.LATE_AFTERNOON,
    DaycycleState.EVENING: Event.EVENING,
    DaycycleState.NIGHT: Event.SUNSET
}

_scenarios = dict()
_event_handlers = dict()

for e in Event:
    _event_handlers[e] = EventHandler('Scenarios/' + e.name.lower())

# == APIs allowing scenarios to subscribe to events and access each other ==

def subscribe(event: Event, callback: Callable):
    '''
    Subscribe to a specified event. Callback will receive
     - Event (always)
     - rabbit: str (if applicable, else None)
     - arguments: dict (if applicable, else empty dict)
    '''
    _event_handlers[event].subscribe(callback)

def unsubscribe(event: Event, callback: Callable):
    '''
    Unregister a callback registered with subscribe()
    '''
    _event_handlers[event].unsubscribe(callback)

def get(name: str) -> object:
    '''
    Get another scenario by name
    '''
    return _scenarios.get(name, None)

# == API for lauching scenarios from other modules ==

def launch(name: str, event: Event, rabbit: str = None, args: dict = {}) -> bool:
    '''
    Asynchronously launch a scenario. Returns True if the scenario exists.
    '''
    module = _scenarios.get(name, None)
    if module is None or not hasattr(module, 'run'):
        return False
    t = Thread(target=module.run, args=[event, rabbit, args], name='Scenario instance')
    t.start()
    return True

# == HTTP API for launching scenarios from webhook ==

'''
Scenarios API for webhook clients
'''
scenarios_api = Blueprint('scenarios_api', __name__)

@scenarios_api.route('/api/v1/scenarios/<name>', methods = ['GET', 'POST'])
@scenarios_api.route('/api/v1/scenarios/<name>/<rabbit>', methods = ['GET', 'POST'])
def scenarios_api_webhook(name, rabbit = None):
    '''
    API for running a scenario
    '''
    # Manually specify target rabbit as GET argument
    if rabbit is not None and not rabbits.is_rabbit(rabbit):
        return 'Invalid request', 400

    # Rabbit not manually specified but request comes from a rabbit
    if rabbit is None and rabbits.is_rabbit(request.remote_addr):
        rabbit = request.remote_addr

    # Request arguments
    if request.method == 'POST':
        args = dict(request.form)
    else:
        args = dict(request.args)

    # Launch scenario
    if launch(name, scenarios.Event.API, rabbit, args):
        return 'OK', 200
    else:
        return 'Not found', 404

# == Load scenarios from disk ==

def _import_module(module_name: str, file_path: str):
    '''
    Load a Python module from specific file
    '''
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

if os.path.isdir('scenarios'):
    for f in os.listdir('scenarios'):
        if f.endswith('.py'):
            file_path = os.path.join('scenarios', f)
            if os.path.isfile(file_path):
                name = f[:-3]
                module_name = 'scenarios.' + name
                module = _import_module(module_name, file_path)
                if hasattr(module, 'run'):
                    _scenarios[name] = module
                    if hasattr(module, 'init'):
                        module.init()
                    logs.debug('Loaded scenario: ' + name)
                else:
                    logs.warning('Module "' + name + '" has no "run" function, ignoring.')

# == Dispatch events from other modules to scenarios ==

def dispatch(event: Event, rabbit: str = None, args: dict = {}):
    '''
    Dispatch an event. Each callback happens on a separate thread.
    '''
    _event_handlers[event].dispatch(event, rabbit, args)

def _nabstate_event_callback(rabbit: str, new_state: str, automated: bool):
    '''
    Listen to nabstate events to run sleep/wakeup events in scenarios
    Automated means thet state change was caused by a scenario/module calling nabstate.set_sleeping()
    '''
    if new_state in _nabstate_to_event:
        dispatch(_nabstate_to_event[new_state], rabbits.get_name(rabbit), {'automated': automated })

def _daycycle_event_callback(current_state: DaycycleState):
    '''
    Listen to daylight events to run sunrise/sunset events in scenarios
    '''
    assert(current_state in _daycycle_to_event)
    dispatch(_daycycle_to_event[current_state])

def _temperature_event_callback(event: TemperatureEvent):
    '''
    Listen to special temperature events to run temperature event in scenarios
    '''
    if event.type != TemperatureEventType.DATA:
        dispatch(Event.TEMPERATURE, rabbit=event.rabbit, args=vars(event))
    else:
        dispatch(Event.TEMPERATURE_DATA, rabbit=event.rabbit, args=vars(event))

def _opening_event_callback(opening_name: str, state: OpenState, shutter_name: str = None, rabbit_name: str = None, is_front_door: bool = False):
    '''
    Listen to opening events to run OPEN_CLOSE event in scenarios
    '''
    dispatch(Event.OPEN_CLOSE, rabbit=rabbit_name, args={'opening': opening_name, 'state': state, 'shutter': shutter_name, 'is_front_door': is_front_door})

def _pcstate_event_callback(computer: str, state: PcState, rabbit_name: str):
    '''
    Listen to pcstate events to run pcstate events in scenarios
    '''
    dispatch(Event.PC_STATE, rabbit=rabbit_name, args={'computer': computer, 'state': state})

nabstate.event_handler.subscribe(_nabstate_event_callback)
daycycle.event_handler.subscribe(_daycycle_event_callback)
temperature.event_handler.subscribe(_temperature_event_callback)
openings.event_handler.subscribe(_opening_event_callback)
pcstate.event_handler.subscribe(_pcstate_event_callback)
