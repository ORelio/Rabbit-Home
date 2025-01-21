#!/usr/bin/env python3

# ==========================================
# switches - map switch events to actions
# switch events come from the enocean module
# By ORelio (c) 2024 - CDDL 1.0
# ==========================================

from configparser import ConfigParser

import time

import actions
import enocean
import scenarios
import rabbits
import notifications

from logs import logs

config = ConfigParser()
config.read('config/switches.ini')

_switches = {}
_device_to_name = {}
_device_to_rabbit = {}

for switch_name in config.sections():
    name = switch_name.lower()
    device = None
    rabbit_name = None
    buttons = {}
    for (key, val) in config.items(switch_name):
        key = key.lower().strip()
        val_lower = val.lower().strip()
        if key == 'device':
            device = val_lower
        elif key == 'rabbit':
            rabbit_name = rabbits.get_name(val_lower)
        else:
            buttons[key] = actions.str2action(val_lower, setting_name='{}/{}'.format(switch_name, key))
    if name in _switches:
        raise ValueError('Duplicate switch name: "{}"'.format(name))
    if device is None:
        raise ValueError('Missing "device" field for "{}"'.format(switch_name))
    if device in _device_to_name:
        raise ValueError('Duplicate device: "{}"'.format(device))
    _switches[name] = buttons
    _device_to_name[device] = name
    if rabbit_name:
        _device_to_rabbit[device] = rabbit_name
    logs.debug('Loaded switch "{}":'.format(name))
    for key in buttons:
        logs.debug('[{}/{}] {}'.format(name, key, buttons[key]))

_last_state = dict()
_last_press = dict()

def _enocean_callback(sender_name: str, switch_or_button_event: object):
    '''
    Handle enocean switch event:
    Find which button of which switch was pressed, and run the associated action.
    '''
    device = 'enocean:{}'.format(sender_name.lower())
    # Retrieve configuration for device which fired the event
    if device in _device_to_name:
        name = _device_to_name[device]
        rabbit = _device_to_rabbit.get(device, None)
        if name in _switches:
            buttons = _switches[name]
            # For each configured button, look for button state in event object
            for key in buttons:
                val = getattr(switch_or_button_event, key, None)
                if val is not None:
                    button = '{}:{}'.format(device, key)
                    if not button in _last_press:
                        _last_press[button] = 0
                        _last_state[button] = False
                    if val: # Pressed
                        logs.info('Pressed {}: {}: {}'.format(name, key, buttons[key]))
                        buttons[key].run(event_type=scenarios.Event.SWITCH, rabbit=rabbit, secondary_action=False)
                        _last_press[button] = time.time()
                        _last_state[button] = True
                        battery_percent = getattr(switch_or_button_event, 'battery_percent', None)
                        if battery_percent is not None:
                            if battery_percent <= 5:
                                logs.warning('Battery low: {} ({}%)'.format(sender_name, battery_percent))
                                notifications.publish('{}: {}%'.format(sender_name, battery_percent), title='Pile faible', tags='battery', rabbit=rabbit)
                    elif type(switch_or_button_event) == enocean.SwitchEvent:
                        # Released
                        if _last_state[button]:
                            # Was previously pressed...
                            if _last_press[button] + 1 < time.time() and _last_press[button] + 30 > time.time():
                                # ... Between 1 and 30 seconds ago => Release after long press
                                logs.info('Released {}: {}: {}'.format(name, key, buttons[key]))
                                buttons[key].run(event_type=scenarios.Event.SWITCH, rabbit=rabbit, secondary_action=True)
                        _last_state[button] = False
        else:
            logs.info('No config for switch "{}"'.format(name))
    else:
        logs.info('No config for device "{}"'.format(device))

enocean.switch_event_handler.subscribe(_enocean_callback)
enocean.button_event_handler.subscribe(_enocean_callback)
enocean.contact_event_handler.subscribe(_enocean_callback)
