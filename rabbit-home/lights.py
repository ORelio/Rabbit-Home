#!/usr/bin/env python3

# ========================================================
# lights - control Shelly lightbulbs through HTTP REST API
# By ORelio (c) 2025 - CDDL 1.0
# ========================================================

from threading import Thread
from configparser import ConfigParser

import json
import requests
import time

from logs import logs

import notifications

_lights = {}
_default_brightness = {}
_default_white = {}
_default_transition = {}

config = ConfigParser()
config.read('config/lights.ini')

API_SWITCH='light/0'
API_SETTINGS='settings/'

# Load configuration file
for light_name_raw in config.sections():
    light_name = light_name_raw.lower()
    light_ip = config.get(light_name_raw, 'IP')
    light_brightness = config.getint(light_name_raw, 'Brightness', fallback=100)
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
    if light_name in _lights:
        raise ValueError('Duplicate light name: {}'.format(light_name_raw))
    _lights[light_name] = light_ip
    _default_brightness[light_name] = light_brightness
    _default_white[light_name] = light_white
    _default_transition[light_name] = light_transition
    logs.debug('Loaded light "{}" (IP={}, Brightness={}, White={}, TransitionMs={})'.format(
        light_name,
        light_ip,
        light_brightness,
        light_white,
        light_transition
    ))
logs.debug('Loaded {} light definitions'.format(len(_lights)))

def _api_request(light: str, api_endpoint: str, parameters: dict = None, retries: int = 2) -> dict:
    '''
    Make a light WebUI API request
    light: name of the light
    api_endpoint: Endpoint to use. See constants defined above.
    parameters: Request parameters (as dict)
    retries: (optional) Amount of HTTP request retries. Nabaztag webserver may be slow on first request.
    returns API response
    '''
    if not light in _lights:
        raise ValueError('Unknown light: {}'.format(light))
    ip = _lights[light]
    try:
        url = f"http://{ip}/{api_endpoint}"
        return json.loads(requests.get(url, params=parameters).text)
    except requests.exceptions.ConnectionError:
        if retries <= 0:
            logs.debug(f"in _api_request({light}, {api_endpoint}, {str(parameters)}, {retries}):")
            raise
        return _api_request(light, api_endpoint, parameters, retries - 1)

def _switch(light: str, on: bool = False, brightness: int = None, white: int = None, transition: int = None) -> bool:
    light = light.lower()
    if not light in _lights:
        raise ValueError('Unknown light: {}'.format(light))

    if not white:
        white = _default_white[light]
    if not transition:
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
    if brightness:
        arguments['brightness'] = str(brightness)
    if on:
        arguments['white'] = str(white)

    logs.info('Adjusting {}: on={}, brightness={}, white={}, transition={}'.format(
        light, on, brightness, white, transition))

    try:
        original_transition = _api_request(light, API_SETTINGS)['transition']
        if original_transition != transition:
            _api_request(light, API_SETTINGS, {'transition': str(transition)})
        _api_request(light, API_SWITCH, arguments)
        if original_transition != transition:
            time.sleep(transition/1000) # wait for transition to finish playing before restoring it
            _api_request(light, API_SETTINGS, {'transition': str(original_transition)})
        return True
    except requests.exceptions.ConnectionError:
        logs.warning('Failed to connect to light "{}"'.format(light))
        notifications.publish("L'éclairage '{}' n'a pas répondu".format(light), title='Eclairage injoignable', tags='electric_plug,bulb')
        return False

def switch(light: str, on: bool = False, brightness: int = None, white: int = None, transition: int = None, synchronous=False) -> bool:
    '''
    Switch a light
    light: Name of light to operate
    on: Desired ON/OFF state, True means ON, False means OFF
    brightness: Desired brightness [0-100], default set in config
    white: Desired warmness from 0 (warm) to 100 (cold), default set in config
    transition: transition delay from 0ms (immediate) to 5000ms (5 seconds), default set in config
    synchronous: Wait for light to finish switching before returning
    '''
    if synchronous:
        return _switch(light, on=on, brightness=brightness, white=white, transition=transition)
    else:
        _switch_thread = Thread(target=_switch, args=[light], kwargs={'on': on, 'brightness': brightness, 'white':white, 'transition': transition }, name='Switching Light')
        _switch_thread.start()
        return True
