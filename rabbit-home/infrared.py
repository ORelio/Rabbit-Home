#!/usr/bin/env python3

# ====================================
# infrared - send IR-Gateway commands
# https://github.com/ORelio/IR-Gateway
# By ORelio (c) 2024 - CDDL 1.0
# ====================================

import requests
import json
import time

from configparser import ConfigParser
from enum import Enum
from logs import logs

_gateway_url = None
_device_addresses = {}
_device_commands = {}

_CONFIG_SECTION_GATEWAY='Gateway'
_CONFIG_SECTION_DEVICES='Devices'

config = ConfigParser()
config.read('config/infrared.ini')
_gateway_url = config.get(_CONFIG_SECTION_GATEWAY, 'URL')

if _gateway_url is None or len(_gateway_url) == 0:
    logs.warning('No Gateway defined in config, Infrared disabled.')
    _gateway_url = None
else:
    for (name, address) in config.items(_CONFIG_SECTION_DEVICES):
        name = name.lower().strip()
        address = int(address.lower().strip())
        if not name in _device_addresses:
            _device_addresses[name] = address
        else:
            logs.warning('Duplicate device name "' + str(name) + '", keeping address=' + str(_device_addresses[name]) + ', skipping address=' + str(address))
    for device_name_raw in config.sections():
        if device_name_raw not in [_CONFIG_SECTION_GATEWAY, _CONFIG_SECTION_DEVICES]:
            device = device_name_raw.lower().strip()
            if device in _device_addresses:
                if device not in _device_commands:
                    commands = {}
                    for (name, id) in config.items(device_name_raw):
                        name = name.lower().strip()
                        id = int(id.lower().strip())
                        if not name in commands:
                            commands[name] = id
                        else:
                            logs.warning('Duplicate command name "{}" for device + "{}", keeping id={}, skipping id={}'.format(name, device, commands[name], id))
                    logs.debug('Loaded device "{}" (address={}) with {} commands'.format(device, _device_addresses[device], len(commands)))
                    _device_commands[device] = commands
                else:
                    logs.warning('Duplicate configuration section for device "{}", keeping the first one.'.format(name))
            else:
                logs.warning('Skipping device without address: {}'.format(device))

def _api_send(address: int, command: int, retries: int=2):
    '''
    Send an Infrared command (IR-Gateway API request)
    address: IR Device Address
    command: IR Device Command
    retries: (optional) Amount of HTTP request retries.
    Returns True if the command was sent successfully
    '''
    try:
        server_address = _gateway_url.strip('/')
        url = server_address + '/ir/send' + '?address=' + str(int(address)) + '&command=' + str(int(command))
        response = requests.get(url, timeout=10)
        respdata = json.loads(response.content)
        return respdata['success'] == True
    except:
        if retries <= 0:
            raise
        _api_send(address, command, retries - 1)

def _api_check():
    '''
    Check API is reachable, with a timeout of 5 seconds
    '''
    try:
        requests.get(_gateway_url, timeout=5)
        return True
    except:
        return False

def send(device: str, command: str, sends: int = 1, delay_seconds: int = 1) -> bool:
    '''
    Send an Infrared command
    device: Name of device to operate
    command: Name of command to send
    Returns True if the command was sent successfully
    sends: amount of sends, minimum is 1, default is to send 1 time
    delay_seconds: delay in seconds between sends, default is to wait 1 second between sends
    returns TRUE if send succeeded
    '''
    if _gateway_url is None:
        logs.error('send() called but no Gateway defined in config.')
        return False
    device = device.lower()
    command = command.lower()
    if device in _device_addresses:
        address = _device_addresses[device]
        if device in _device_commands and command in _device_commands[device]:
            command_id = _device_commands[device][command]
            logs.info('Sending command {} to {} ({} send{})'.format(command, device, sends, 's' if sends > 1 else ''))
            try:
                for i in range(sends):
                    if not _api_send(address, command_id):
                        return False
                    if sends > 1:
                        time.sleep(delay_seconds)
            except Exception as ex:
                logs.warning('Failed to send command: ' + type(ex).__name__)
                return False
        else:
            raise ValueError('Unknown command "' + str(command) + '" for device "' + str(device) + '"')
    else:
        raise ValueError('Unknown device: ' + str(device))

def wait_for_gateway(timeout_seconds: int):
    '''
    Wait for the Infrared gateway to become reachable
    In case the gateway is connected to a power socket that was just turned on
    timeout_seconds: Maximum delay to wait (minimum: 5 seconds)
    '''
    if timeout_seconds < 5:
        timeout_seconds = 5
    attempts = int(timeout_seconds / 5)
    for i in range(attempts):
        if _api_check():
            return True
    return False
