#!/usr/bin/env python3

# ==============================================================================
# plugs433 - control 433Mhz plugs using codesend tool and GPIO (Raspberry Pi...)
# Uses 'codesend' command. See utilities/codesend folder for setup instructions
# By ORelio (c) 2024 - CDDL 1.0
# ==============================================================================

from flask import Blueprint, jsonify
from threading import Thread, Lock

import subprocess
import time

from configparser import ConfigParser

from logs import logs

_devices = {}
_device_state = {}
_state_lock = Lock()

_DEVICE_COMMAND="codesend"
_SEND_COMMAND_DELAY=0.1
_command_lock = Lock()

config = ConfigParser()
config.read('config/plugs433.ini')

def _calculate_code(channel: str, unit: str, on: bool) -> int:
    '''
    Calculate a 443MHz code to send for turning the specified device ON or OFF
    channel: "SYSTEM-CODE" Sequence of switches set on the device, e.g. '10011' (Defines a channel)
    unit: "UNIT-CODE" Switches set on the device (A/B/C/D/E), e.g. 'A' (Defines a device)
    on: TRUE to turn the device ON, FALSE to turn the device OFF
    returns the 433MHz code to send as int
    Remarks:
    - In channel, '1' means switch set UP (ON), '0' means switch set DOWN (OFF)
    - It is possible to set multiple letters at a time in unit code, e.g. 'ABCDE'.
    - As long as the corresponding set of switches is enabled on the device, it will respond.
    - Devices with multiple letters in unit code will not work with the bundled remote
    '''
    # How the protocol works:
    #  Each plug has 5 switches for system code, and 5 switches for unit code
    #  System code is some kind of "channel", unit code is "A/B/C/D/E"
    #  The bundled remote has 5 switches to set the system code to the same value
    #  It also has A/B/C/D ON/OFF buttons to send ON/OF commands for devices in the "channel"
    #  When pressing a button, the remote sends a code (integer). Example:
    #               [ -- System --][ -- Unit -- ] ## [ON/OFF]
    #                1  0  0  1  1  A  B  C  D  E ## ON
    #  10011 A ON = 01 00 00 01 01 00 01 01 01 01 00 01
    #             = 4277585 <- this is the code sent over the air
    #  Note that byte values for switches are reversed in protocol:
    #  Switch UP (in direction marked "ON" on the device) gives bit 0 in protocol
    #  The remote assumes that only one letter is "ON" ('0') so every other letter is set to '1'
    unit_codes = 'ABCDE'
    unit = unit.upper()
    if len(channel) != 5:
        raise ValueError('channel must be a sequence of 5 digits (0 or 1)')
    for c in channel:
        if c != '0' and c != '1':
            raise ValueError('channel must be a sequence of 5 digits (0 or 1)')
    if len(unit) < 1 or len(unit) > 5:
        raise ValueError('unit must be 1-5 uppercase letter(s): A, B, C, D, E')
    for c in unit:
        if not c in unit_codes:
            raise ValueError('unit must be 1-5 uppercase letter(s): A, B, C, D, E')
    binary_code = ''
    for c in channel:
        binary_code = binary_code + '0'
        binary_code = binary_code + ('1' if c == '0' else '0')
    for c in unit_codes:
        binary_code = binary_code + '0'
        binary_code = binary_code + ('0' if c in unit else '1')
    binary_code = binary_code + '000'
    binary_code = binary_code + ('1' if on else '0')
    return int(binary_code, 2)

def switch(device: str, state: bool, sends: int = 3, delay_seconds: int = 1):
    '''
    Switch a 433MHz plug
    device: Name of plug to operate
    state: Desired ON/OFF state, True means ON, False means OFF
    sends: amount of sends, minimum is 1, default is to send 3 times
    delay: delay in seconds between sends, default is to wait 1 second between sends
    '''
    device = device.lower()
    if sends < 1:
        sends = 1
    if delay_seconds < 0:
        delay_seconds = 0
    if device in _devices:
        device_data = _devices[device].split(':')
        channel = device_data[0]
        unit = device_data[1]
        state_str = 'ON' if state else 'OFF'
        logs.info('Setting state {} for device {} ({} send{})'.format(
            state_str, device, sends, 's' if sends > 1 else ''))
        with _state_lock:
            _device_state[device] = state
        for i in range(sends):
            with _command_lock:
                command_code = str(_calculate_code(channel, unit, state))
                try:
                    subprocess.run([_DEVICE_COMMAND, command_code], stdout=subprocess.DEVNULL)
                except OSError as os_error:
                    logs.error('Error running command: {}'.format(_DEVICE_COMMAND, command_code))
                    logs.error(os_error)
                time.sleep(_SEND_COMMAND_DELAY) # Minimum delay between 2 commands
            if sends > 1:
                time.sleep(delay_seconds)
                with _state_lock:
                    if _device_state[device] != state:
                        break # Cancel additional sends if the desired state changed
    else:
        raise ValueError('Unknown device: ' + str(device))

for name in config.options('Plugs'):
    device_code = config.get('Plugs', name)
    display_name = name.lower()
    if display_name in _devices:
        raise ValueError('Duplicate plug name: ' + display_name)
    device_data = device_code.split(':')
    if len(device_data) != 2:
        raise ValueError('Invalid plug data for {}: "{}". Expecting [01]{5}:[ABCDE]{1,5}'.format(display_name, device_code))
    try:
        _calculate_code(device_data[0], device_data[1], True)
    except ValueError as e:
        raise ValueError('Invalid plug data for {}: "{}". Expecting [01]{5}:[ABCDE]{1,5}'.format(display_name, device_code))
    _devices[display_name] = device_code
logs.debug('Loaded {} plug aliases: {}'.format(len(_devices), ', '.join(list(_devices.keys()))))

# === HTTP API ===

plugs_api = Blueprint('plugs_api', __name__)

@plugs_api.route('/api/v1/plugs', methods = ['GET'])
def plugs433_api_get():
    devices = {}
    for device in _devices:
        devices[device] = _device_state.get(device, None)
    return jsonify(devices)

@plugs_api.route('/api/v1/plugs/<device>/<state>', methods = ['POST'])
def plugs433_api_set(device, state):
    if not device or not device.lower() in _devices:
        return jsonify({'success': False, 'message': 'Not Found'}), 404
    if not state or not state.upper() in ['ON', 'OFF']:
        return jsonify({'success': False, 'message': 'Invalid parameter'}), 400
    device = device.lower()
    state = (state.upper() == 'ON')
    Thread(target=switch, args=[device, state], name='Plugs433 API SetState').start()
    logs.info('Web API: Switching device {}'.format(device))
    return ({'success': True, 'state': _device_state.get(device, None)})
