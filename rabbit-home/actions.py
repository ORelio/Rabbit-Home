#!/usr/bin/env python3

# ===============================================================
# action - map config entries to actions for use by other modules
# By ORelio (c) 2024 - CDDL 1.0
# ===============================================================

import json
import requests

from logs import logs
from shutters import ShutterState

import shutters
import shutters_auto
import plugs433
import nabstate
import nabweb

# Defer import to avoid circular dependency
# scenarios -> pcstate -> actions -> scenarios
#import scenarios

def str2action(action: str, setting_name: str = None) -> 'Action':
    '''
    Convert setting (str) to action (object)
    type:name[:data] => object representation
    raises ValueError for invalid syntax or unavailable action type

    Supported actions:
     scenario:scenario_name[:{"arg1":"value", "arg2:"value"}]
     shutter:shutter_name:operation[/operation_on_release_long_press]
     plug:plug_name:on|off[/on|off <- operation_on_release_long_press]
     webhook:url <- example: http://example.com/?mywebhook
     sleep[:rabbit_name]
     weather[:rabbit_name]
     airquality[:rabbit_name]
     taichi[:rabbit_name]

    Notes:
     ([text in brackets] means optional part in action data)
     (a|b means use one of the specified values a OR b)
     shutter_name can be several shutters: shutterone+shuttertwo
     omitting rabbit_name is possible for rabbit-related events such as rfid
    '''
    if not setting_name:
        setting_name = '<unknown setting>'

    action_fields = action.split(':')
    if len(action_fields) < 1:
        raise ValueError('Invalid action format for "{}", expecting {}, got "{}"'.format(
            setting_name, 'type:[name[:data]]', action))

    action_type = action_fields[0].lower()
    action_name = action_fields[1] if len(action_fields) > 1 else None
    action_data = action[len(action_type) + len(action_name) + 2:] if len(action_fields) > 2 else None
    action_name_and_data = action[len(action_type) + 1:] if len(action_fields) > 1 else None

    if action_type == 'scenario':
        return ScenarioAction(action_name, action_data)
    elif action_type == 'shutter':
        return ShutterAction(action_name, action_data)
    elif action_type == 'plug':
        return PlugAction(action_name, action_data)
    elif action_type == 'webhook':
        return WebhookAction(action_name_and_data, None)
    elif action_type == 'sleep':
        return SleepAction(action_name, action_data)
    elif action_type == 'weather':
        return WeatherAction(action_name, action_data)
    elif action_type == 'airquality':
        return AirQualityAction(action_name, action_data)
    elif action_type == 'taichi':
        return TaichiAction(action_name, action_data)
    else:
        raise ValueError('Unknown action type for "{}", expecting {}, got "{}"'.format(
        setting_name, 'scenario|shutter|plug|webhook|sleep|weather|airquality|taichi', action_type))

class Action:
    '''
    Represents a generic action having a run() function
    event_type is necessary for scenario actions, ignored otherwise. Must be of type scenarios.Event.
    rabbit is passed to scenarios or used for rabbit-related actions, ignored otherwise.
    secondary_action is set by switches.py when releasing a button. Must be ignored when not used.
    '''
    def __init__(self, name: str, data: str = None):
        raise NotImplementedError('__init__ not implemented.')
    def run(self, event_type = None, rabbit = None, secondary_action: bool = False):
        raise NotImplementedError('run() not implemented.')
    def __repr__(self):
        raise NotImplementedError('__repr__ not implemented.')

class ScenarioAction(Action):
    '''
    Launch a scenario (scenario.py)
    '''
    def __init__(self, name: str, data: str = None):
        self.scenario = name
        self.args = json.loads(data) if data else dict()
    def run(self, event_type = None, rabbit = None, secondary_action: bool = False):
        # Deferred import to avoid circular dependency
        import scenarios
        if not secondary_action:
            scenarios.launch(self.scenario, event_type, rabbit, self.args)
    def __repr__(self):
        return 'ScenarioAction(Scenario: {}, Args: {})'.format(self.scenario, self.args)

class ShutterAction(Action):
    '''
    Move a shutter (shutters.py and optionally shutters_auto.py)
    '''
    def __init__(self, name: str, data: str = None):
        self.shutters = name.split('+')
        if data is None:
            raise ValueError('ShutterAction: Missing action for "{}"'.format(name))
        states = data.split('/')
        if len(states) > 2:
            raise ValueError('ShutterAction: Invalid operation format for "{}", got "{}", expecting {}'.format(
                name, data, 'op or op/op_long'))
        self.state = ShutterState[states[0].upper()]
        self.state_long = ShutterState[states[1].upper()] if len(states) > 1 else None
    def run(self, event_type = None, rabbit = None, secondary_action: bool = False):
        if secondary_action:
            if self.state_long is not None:
                for shutter in self.shutters:
                    #shutters.operate(shutter, self.state_long)
                    shutters_auto.operate(shutter, self.state_long, direct_command=True)
            else:
                logs.info('ShutterAction({}): No Release action'.format(', '.join(self.shutters)))
        else:
            for shutter in self.shutters:
                #shutters.operate(shutter, self.state)
                shutters_auto.operate(shutter, self.state, direct_command=True)
    def __repr__(self):
        return 'ShutterAction(Shutter: {}, State: {}, StateReleaseLong: {})'.format(
            ', '.join(self.shutters), self.state, self.state_long)

class PlugAction(Action):
    '''
    Turn ON or OFF a power socket
    '''
    def __init__(self, name: str, data: str = None):
        self.plug = name
        if data is None:
            raise ValueError('PlugAction: Missing state for "{}"'.format(name))
        states = data.split('/')
        if len(states) > 2:
            raise ValueError('PlugAction: Invalid state format for "{}", got "{}", expecting {}'.format(
                name, data, 'op or op/op_long'))
        for state in states:
            if state is None or state.lower() not in ['on', 'off']:
                raise ValueError('PlugAction: Missing or invalid state for "{}", got "{}"'.format(name, state))
        self.state = states[0].lower() == 'on'
        self.state_long = states[1].lower() == 'on' if len(states) > 1 else None
    def run(self, event_type = None, rabbit = None, secondary_action: bool = False):
        if secondary_action:
            if self.state_long is not None:
                plugs433.switch(self.plug, self.state_long)
        else:
            plugs433.switch(self.plug, self.state)
    def __repr__(self):
        return 'PlugAction(Plug: {}, State: {}, StateReleaseLong: {})'.format(self.plug, self.state, self.state_long)

class WebhookAction(Action):
    '''
    Call the specified URL (HTTP GET)
    '''
    def __init__(self, name: str, data: str = None):
        self.url = name
    def run(self, event_type = None, rabbit = None, secondary_action: bool = False):
        if not secondary_action:
            try:
                requests.get(self.url, timeout=30).raise_for_status()
                logs.info('Called webhook URL: {}'.format(self.url))
            except:
                logs.error('Failed to call webhook URL: {}'.format(self.url))
    def __repr__(self):
        return 'WebhookAction({})'.format(self.url)

class SleepAction(Action):
    '''
    Put a rabbit to sleep by overriding its sleep hours settings
    '''
    default_rabbit = None
    def __init__(self, name: str, data: str = None):
        self.default_rabbit = name
    def run(self, event_type = None, rabbit = None, secondary_action: bool = False):
        if (rabbit or self.default_rabbit) and not secondary_action:
            nabstate.set_sleeping(rabbit if rabbit else self.default_rabbit, sleeping=True, play_sound=True)
    def __repr__(self):
        return 'SleepAction({})'.format(self.default_rabbit)

class WeatherAction(Action):
    '''
    Launch Weather action on a rabbit
    '''
    default_rabbit = None
    def __init__(self, name: str, data: str = None):
        self.default_rabbit = name
    def run(self, event_type = None, rabbit = None, secondary_action: bool = False):
        if (rabbit or self.default_rabbit) and not secondary_action:
            nabweb.launch_weather(rabbit if rabbit else self.default_rabbit)
    def __repr__(self):
        return 'WeatherAction({})'.format(self.default_rabbit)

class AirQualityAction(Action):
    '''
    Launch Air Quality action on a rabbit
    '''
    default_rabbit = None
    def __init__(self, name: str, data: str = None):
        self.default_rabbit = name
    def run(self, event_type = None, rabbit = None, secondary_action: bool = False):
        if (rabbit or self.default_rabbit) and not secondary_action:
            nabweb.launch_airquality(rabbit if rabbit else self.default_rabbit)
    def __repr__(self):
        return 'AirQualityAction({})'.format(self.default_rabbit)

class TaichiAction(Action):
    '''
    Launch Taichi action on a rabbit
    '''
    default_rabbit = None
    def __init__(self, name: str, data: str = None):
        self.default_rabbit = name
    def run(self, event_type = None, rabbit = None, secondary_action: bool = False):
        if (rabbit or self.default_rabbit) and not secondary_action:
            nabweb.launch_taichi(rabbit if rabbit else self.default_rabbit)
    def __repr__(self):
        return 'TaichiAction({})'.format(self.default_rabbit)
