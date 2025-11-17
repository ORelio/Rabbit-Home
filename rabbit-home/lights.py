#!/usr/bin/env python3

# ========================================================
# lights - control Shelly lightbulbs through HTTP REST API
# By ORelio (c) 2025 - CDDL 1.0
# ========================================================

from flask import Blueprint, jsonify
from threading import Thread, Lock
from configparser import ConfigParser

import json
import requests
import time

from logs import logs

import notifications
import plugs433
import rabbits

_lights = {}
_channels = {}
_default_brightness = {}
_default_white = {}
_default_transition = {}

_command_locks = {}
_command_tokens = {}

_light_state = {}
_state_lock = Lock()

_rabbit_to_lights = {}
_lights_to_rabbit = {}

config = ConfigParser()
config.read('config/lights.ini')

PLUG_PREFIX='plug:'

API_SWITCH='light/{CHANNEL}'
API_SETTINGS='settings/'

# Load configuration file
for light_name_raw in config.sections():
    light_name = light_name_raw.lower()
    light_ip = config.get(light_name_raw, 'IP')
    light_channel = config.getint(light_name_raw, 'Channel', fallback=0)
    light_brightness = config.getint(light_name_raw, 'Brightness', fallback=100)
    if light_channel < 0:
        raise ValueError('Negative channel invalid for light: {}'.format(light_name_raw))
    if light_brightness < 1:
        light_brightness = 1
    if light_brightness > 100:
        light_brightness = 100
    light_white = config.getint(light_name_raw, 'White', fallback=50)
    if light_white < 0:
        light_white = 0
    if light_white > 100:
        light_white = 100
    light_transition = config.getint(light_name_raw, 'TransitionMs', fallback=500)
    if light_transition < 0:
        light_transition = 0
    if light_transition > 5000:
        light_transition = 5000
    rabbit = rabbits.get_name(config.get(light_name_raw, 'Rabbit', fallback=None))
    if light_name in _lights:
        raise ValueError('Duplicate light name: {}'.format(light_name_raw))
    if rabbit:
        if not rabbit in _rabbit_to_lights:
            _rabbit_to_lights[rabbit] = []
        _rabbit_to_lights[rabbit].append(light_name)
        _lights_to_rabbit[light_name] = rabbit
    _lights[light_name] = light_ip
    _channels[light_name] = light_channel
    _default_brightness[light_name] = light_brightness
    _default_white[light_name] = light_white
    _default_transition[light_name] = light_transition
    _command_locks[light_name] = Lock()
    _command_tokens[light_name] = 0;
    logs.debug('Loaded light "{}" (IP={}, Brightness={}, White={}, TransitionMs={}, Rabbit={})'.format(
        light_name,
        light_ip,
        light_brightness,
        light_white,
        light_transition,
        rabbit
    ))
logs.debug('Loaded {} light definitions'.format(len(_lights)))

def _api_request(light: str, api_endpoint: str, parameters: dict = None, retries: int = 2) -> dict:
    '''
    Make a light WebUI API request
    light: name of the light
    api_endpoint: Endpoint to use. See constants defined above.
    parameters: Request parameters (as dict)
    retries: (optional) Amount of HTTP request retries
    returns API response
    '''
    light = light.lower()
    if not light in _lights:
        raise ValueError('Unknown light: {}'.format(light))
    try:
        ip = _lights[light]
        url = f"http://{ip}/{api_endpoint}"
        return json.loads(requests.get(url, params=parameters).text)
    except (requests.exceptions.ConnectionError, json.decoder.JSONDecodeError) as err:
        if retries <= 0:
            logs.debug(f"in _api_request({light}, {api_endpoint}, {str(parameters)}, {retries}):")
            raise
        return _api_request(light, api_endpoint, parameters, retries - 1)

def _sleep(thread_token: int, light: str, delay_milliseconds: int):
    '''
    Sleep for the specified delay but stop early if the token changed
    Note: The sleep delay resolution is 100ms rounded to the upper unit, e.g, 50ms is rounded to 100ms and so on.
    '''
    if delay_milliseconds > 0:
        for i in range(0, delay_milliseconds, 100):
            if _command_tokens.get(light, 0) == thread_token:
                time.sleep(0.1)

def _switch(thread_token: int, light: str, on: bool = False, brightness: int = None, white: int = None, transition: int = None, delay: int = None, delay_off: int = None):
    '''
    Switch a light (internal). See switch()
    thread_token: Allows cancelling a delayed on/off operations by updating the token.
    '''
    light = light.lower()
    if not light in _lights:
        raise ValueError('Unknown light: {}'.format(light))

    if white is None:
        white = _default_white[light]
    if transition is None:
        transition = _default_transition[light]

    if brightness is not None:
        on = True
        if brightness == 0:
            on = False
            brightness = None
            white = None
    elif on is not None:
        brightness = _default_brightness[light] if on else None
    else:
        raise ValueError('Missing desired state: "on" or "brightness"')

    arguments = {'turn': 'on' if on else 'off'}
    if brightness is not None:
        arguments['brightness'] = str(brightness)
    if white is not None:
        arguments['white'] = str(white)

    logs.info('Adjusting {}: on={}, brightness={}, white={}, transition={}'.format(
        light, on, brightness, white, transition))

    if delay:
        _sleep(thread_token, light, delay)

    with _command_locks[light]:
        try:
            if _command_tokens.get(light, 0) == thread_token:

                if _lights[light].startswith(PLUG_PREFIX):
                    # Light is connected through its power socket, only on/off state is supported
                    plugs433.switch(_lights[light].split(':')[1].lower(), state=on)
                else:
                    # Temporarily update the light transition setting if needed
                    original_transition = transition
                    original_settings = _api_request(light, API_SETTINGS)
                    if 'transition' in original_settings:
                        original_transition = original_settings['transition']
                    if original_transition != transition:
                        _api_request(light, API_SETTINGS, {'transition': str(transition)})

                    # Switch light to desired brightness and color
                    if _command_tokens.get(light, 0) == thread_token:
                        _api_request(light, API_SWITCH.replace('{CHANNEL}', str(_channels[light])), arguments)
                        with _state_lock:
                            _light_state[light] = {
                                'on': on,
                                'brightness': brightness,
                                'white': white
                            }

                    # Wait for transition to finish playing before restoring it
                    if original_transition != transition:
                        _sleep(thread_token, light, transition)
                        _api_request(light, API_SETTINGS, {'transition': str(original_transition)})

        except requests.exceptions.ConnectionError:
            logs.warning('Failed to connect to light "{}"'.format(light))
            notifications.publish("L'éclairage '{}' n'a pas répondu".format(light), title='Eclairage injoignable', tags='electric_plug,bulb', rabbit=_lights_to_rabbit.get(light, None))

    if delay_off is not None:
        _switch(thread_token, light, on=False, transition=transition, delay=delay_off)

def switch(light: str, on: bool = False, brightness: int = None, white: int = None, transition: int = None, delay: int = None, delay_off: int = None, synchronous: bool = False):
    '''
    Switch a light
    light: Name of light to operate
    on: Desired ON/OFF state, True means ON, False means OFF
    brightness: Desired brightness [0-100], default set in config
    white: Desired warmness from 0 (warm) to 100 (cold), default set in config
    transition: transition delay from 0ms (immediate) to 5000ms (5 seconds), default set in config
    delay: delay before switching the light from 0ms (immediate) to any value in milliseconds, default 0ms
    delay_off: timeout delay before auto-switching the light off, from None (never) to any value in milliseconds, default Never
    synchronous: Wait for light to finish switching before returning
    '''
    light = light.lower()
    if not light in _lights:
        raise ValueError('Unknown light: {}'.format(light))

    with _command_locks[light]:
        thread_token = round(time.time() * 1000)
        _command_tokens[light] = thread_token

    if synchronous:
        _switch(thread_token, light, on=on, brightness=brightness, white=white, transition=transition, delay=delay, delay_off=delay_off)
    else:
        _switch_thread = Thread(target=_switch,
            args=[thread_token, light],
            kwargs={'on': on, 'brightness': brightness, 'white':white, 'transition': transition, 'delay': delay, 'delay_off': delay_off },
            name='Switching Light')
        _switch_thread.start()

def get_for_rabbit(rabbit: str) -> list:
    '''
    Get all lights associated with a rabbit
    '''
    rabbit = rabbits.get_name(rabbit)
    if not rabbit in _rabbit_to_lights:
        return []
    return _rabbit_to_lights[rabbit]

def switch_for_rabbit(rabbit: str, on: bool = False, brightness: int = None, white: int = None, transition: int = None, delay: int = None, delay_off: int = None):
    '''
    Switch all lights associated with a rabbit
    on: Desired ON/OFF state, True means ON, False means OFF
    brightness: Desired brightness [0-100], default set in config
    white: Desired warmness from 0 (warm) to 100 (cold), default set in config
    transition: transition delay from 0ms (immediate) to 5000ms (5 seconds), default set in config
    delay: delay before switching the light from 0ms (immediate) to any value in milliseconds, default 0ms
    delay_off: timeout delay before auto-switching the light off, from None (never) to any value in milliseconds, default Never
    '''
    lights = get_for_rabbit(rabbit)
    for light in lights:
        switch(light, on=on, brightness=brightness, white=white, transition=transition, delay=delay, delay_off=delay_off)

# === HTTP API ===

lights_api = Blueprint('lights_api', __name__)

@lights_api.route('/api/v1/lights', methods = ['GET'])
def lights_api_get():
    lights = {}
    for light in _lights:
        state = None
        with _state_lock:
            state = _light_state.get(light, None)
            if not state:
                state = {
                    'on': None,
                    'brightness': None,
                    'white': None
                }
        state['dimmable'] = not _lights[light].startswith(PLUG_PREFIX)
        lights[light] = state
    return jsonify(lights)
