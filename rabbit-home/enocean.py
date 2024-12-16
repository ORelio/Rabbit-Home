#!/usr/bin/env python3

# ==============================================================================================
# enocean - listen to enocean events using USB to serial adapter
# By ORelio (c) 2024 - CDDL 1.0
# Uses 'enoceanserial' command to connect to the dongle over serial and read incoming messages
# See utilities/enoceanserial folder for source code and setup instructions
# Serial protocol references:
# https://www.enocean.com/wp-content/uploads/Knowledge-Base/EnOceanSerialProtocol3-1.pdf
# https://www.enocean-alliance.org/wp-content/uploads/2020/07/EnOcean-Equipment-Profiles-3-1.pdf
# https://tools.enocean-alliance.org/EEPViewer/profiles/D2/03/0A/D2-03-0A.pdf
# https://tools.enocean-alliance.org/EEPViewer/profiles/F6/02/01/F6-02-01.pdf
# https://tools.enocean-alliance.org/EEPViewer/profiles/A5/02/05/A5-02-05.pdf
# https://tools.enocean-alliance.org/EEPViewer/profiles/A5/02/13/A5-02-13.pdf
# https://tools.enocean-alliance.org/EEPViewer/profiles/A5/02/13/D5-00-01.pdf
# ==============================================================================================

from typing import Callable
from threading import Thread
from configparser import ConfigParser
from dataclasses import dataclass
from enum import Enum

import platform
import crc8
import shutil
import subprocess

from events import EventHandler
from logs import logs

# == Protocol constants ==

_ENOCEAN_SERIAL_COMMAND = "enoceanserial"
_PACKET_TYPE_RADIO = 0x01
_RADIO_TYPE_RPS = 0xF6
_RADIO_TYPE_1BS = 0xD5
_RADIO_TYPE_4BS = 0xA5
_RADIO_TYPE_VLD = 0xD2

class EnoceanProfile(Enum): # List of currently implemented equipment profiles
    D2_03_0A = 1, # Push Button – Single Button
    F6_02_01 = 2, # Rocker Switch, 2 Rocker - Light and Blind Control - Application Style 1
    A5_02_05 = 3, # Temperature Sensor Range 0°C to +40°C
    A5_02_13 = 4, # Temperature Sensor Range -30°C to +50°C
    D5_00_01 = 5  # Single Input Contact Switch

# == Load configuration file ==

_name_to_device = dict()
_device_to_name = dict()
_device_to_profile = dict()

def load_config():
    config = ConfigParser()
    config.read('config/enocean.ini')
    for name in config.options('Devices'):
        device_info = config.get('Devices', name)
        display_name = name.lower()
        device_data = device_info.split(':')
        if len(device_data) != 2:
            raise ValueError('Invalid device data for {}: "{}". Expecting {}'.format(
                display_name, device_info, '[0-9A-F](8):[0-9A-F](2)-[0-9A-F](2)-[0-9A-F](2)'))
        device_id = device_data[0].lower()
        try:
            if len(device_id) != 8:
                raise ValueError('Invalid device ID length, expecting 8 characters')
            int(device_id, 16)
        except ValueError:
            raise ValueError('Invalid device ID for {}: "{}". Expecting [0-9A-F](8)'.format(display_name, device_id))
        if display_name in _name_to_device:
            raise ValueError('Duplicate device name: ' + display_name)
        if device_id in _device_to_name:
            raise ValueError('Duplicate device ID: ' + device_id)
        device_profile = device_data[1].upper()
        device_profile_parts = device_profile.split('-')
        try:
            if len(device_profile) != 8:
                raise ValueError('Invalid device EEP length, expecting 8 characters')
            if len(device_profile_parts) != 3 \
                or len(device_profile_parts[0]) != 2 \
                or len(device_profile_parts[1]) != 2 \
                or len(device_profile_parts[2]) != 2:
                    raise ValueError('Invalid device EEP format, expecting XX-XX-XX')
            int(device_profile_parts[0], 16)
            int(device_profile_parts[1], 16)
            int(device_profile_parts[2], 16)
        except ValueError:
            raise ValueError('Invalid device EEP format for {}: "{}". Expecting {}'.format(
                display_name, device_profile, '[0-9A-F](2)-[0-9A-F](2)-[0-9A-F](2)'))
        device_profile_enum = device_profile.replace('-', '_')
        try:
            EnoceanProfile[device_profile_enum]
        except KeyError:
            raise ValueError('Unknown device EEP for {}: "{}" - Not implemented.'.format(display_name, device_profile))
        _name_to_device[display_name] = device_id
        _device_to_name[device_id] = display_name
        _device_to_profile[device_id] = EnoceanProfile[device_profile_enum]
        logs.debug('Loaded device: {} (ID={}, EEP={})'.format(display_name, device_id, device_profile))

# == Event mechanism ==

@dataclass
class SwitchEvent:
    pressed: bool
    left_bottom: bool
    left_top: bool
    right_bottom: bool
    right_top: bool

@dataclass
class ButtonEvent():
    battery_percent: int
    single_press: bool
    double_press: bool
    long_press: bool
    release_long: bool

@dataclass
class ContactEvent:
    closed: bool

@dataclass
class TemperatureEvent():
    temperature: float

'''
Switch Event Handler
Callbacks will receive args = (sender_name: str, switch_event: enocean.SwitchEvent)
'''
switch_event_handler = EventHandler('Enocean/Switch')

'''
Button Event Handler
Callbacks will receive args = (sender_name: str, button_event: enocean.ButtonEvent)
'''
button_event_handler = EventHandler('Enocean/Button')

'''
Contact Event Handler
Callbacks will receive args = (sender_name: str, contact_event: enocean.ContactEvent)
'''
contact_event_handler = EventHandler('Enocean/Contact')

'''
Temperature Event Handler
Callbacks will receive args = (sender_name: str, temperature_event: enocean.TemperatureEvent)
'''
temperature_event_handler = EventHandler('Enocean/Temperature')

def _dispatch_event(event_handler: EventHandler, sender_id: str, event_arg):
    '''
    Dispatch an event to the specified event handler
    event_handler: an event handler, e.g. switch_event_handler
    event_arg: object to pass to event callbacks
    '''
    event_handler.dispatch(_device_to_name.get(sender_id, 'Unknown/' + sender_id), event_arg)

# == Logging utilities ==

def packet_type_format(pkt_type: int) -> str:
    '''
    Format packet type ID for logging
    '''
    return '{}/{}'.format(hex(pkt_type)[2:].upper(), {
        0x00: 'RESERVED',
        _PACKET_TYPE_RADIO: 'Radio',
        0x02: 'Response',
        0x03: 'Radio_Sub_Tel',
        0x04: 'Event',
        0x05: 'Common_Command',
        0x06: 'Smart_Ack_Command',
        0x07: 'Remote_Man_Command',
    }.get(pkt_type, 'UNKNOWN'))

def device_id_format(device_id: str) -> str:
    '''
    Format device ID for logging
    '''
    device_id = device_id.lower()
    device_name = _device_to_name.get(device_id, 'Unknown')
    device_profile = str(_device_to_profile.get(device_id, 'Unknown')).replace('EnoceanProfile.', '').replace('_', '-')
    return '{}/{}/{}'.format(device_id, device_name, device_profile).replace('Unknown/Unknown', 'Unknown')

def radio_type_format(sender_id: str, radio_type: int) -> str:
    '''
    Format radio packet type ID for logging
    '''
    radio_type_hex = hex(radio_type)[2:].upper()
    result = '{}/{}'.format(radio_type_hex, {
        _RADIO_TYPE_RPS: 'RPS',
        _RADIO_TYPE_1BS: '1BS',
        _RADIO_TYPE_4BS: '4BS',
        _RADIO_TYPE_VLD: 'VLD',
        0xD1: 'MSC',
        0xA6: 'ADT',
        0xC6: 'SM_LRN_REQ',
        0xC7: 'SM_LRN_ANS',
        0xA7: 'SM_REC',
        0xC5: 'SYS_EX',
        0x30: 'SEC',
        0x31: 'SEC_ENCAPS',
    }.get(radio_type, 'UNKNOWN'))
    device_profile = _device_to_profile.get(sender_id, None)
    if device_profile is not None:
        if device_profile.name[:2].upper() != radio_type_hex:
            result = '{}/Not supported for {}'.format(result, '' + device_profile.name.replace('_', '-'))
    return result

# == Enocean protocol ==

def bytes2int(b: bytes) -> int:
    '''
    Convert big-endian multi-byte sequence into an int
    '''
    return int.from_bytes(b, byteorder='big')

_crc_hash = crc8.crc8()

def crc8check(b: bytes, expected_crc: bytes) -> bool:
    '''
    Check that provided bytes match the specified CRC8 checksum
    '''
    return _crc_hash.reset().update(b).digest() == expected_crc

def get_bit(b: int, offset: int) -> bool:
    '''
    Get bit as boolean from specified zero-based offset.
    0 = first bit (left), 7 = last bit (right)
    01234567 <- offset
    XXXXXXXX <- byte
    returns TRUE if the specified byte is 1
    '''
    return ((b >> (7 - offset)) & 1) == 1

def is_profile(sender_id: str, profile: EnoceanProfile) -> bool:
    '''
    Check if sender matches the specified profile
    '''
    return sender_id in _device_to_profile and _device_to_profile[sender_id] == profile

def read_packets():
    '''
    Read enocean packets from serial
    '''
    if platform.system() == 'Windows':
        logs.warning('Reading packets from serial is not implemented for Windows')
        return

    command = shutil.which(_ENOCEAN_SERIAL_COMMAND)

    if command is None:
        logs.warning('Command "{}" not found, will not read packets'.format(_ENOCEAN_SERIAL_COMMAND))
        return

    enocean_process = subprocess.Popen([command],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    serial = enocean_process.stdout

    while True:
        try:
            # Advance to next Sync. Byte
            while serial.read(1)[0] != 0x55:
                pass

            # Read packet header
            header = serial.read(4)
            data_len = bytes2int(header[:2])
            opt_data_len = int(header[2])
            pkt_type = int(header[3])
            header_crc = serial.read(1)
            if not crc8check(header, header_crc):
                continue # As per specs, move on to the next Sync. Byte on CRC8H mismatch.

            # Read packet body
            data = serial.read(data_len)
            opt_data = serial.read(opt_data_len)
            data_crc = serial.read(1)
            if not crc8check(data + opt_data, data_crc):
                continue # No guidance in specs for handling invalid packets. Ignoring it.

            # We got a valid packet, decode it
            decode_packet(pkt_type, data, opt_data)
        except IndexError:
            logs.warning('Failed to read packets from serial')
            break

def decode_packet(pkt_type: int, data: bytes, opt_data: bytes):
    '''
    Decode enocean packets received from serial
    '''
    if (pkt_type == _PACKET_TYPE_RADIO):
        decode_radio_packet(data, opt_data)
    else:
        logs.debug('[{}/Not implemented] {}'.format(packet_type_format(pkt_type), data.hex()))

def decode_radio_packet(data: bytes, opt_data: bytes):
    '''
    Decode enocean RADIO packets
    '''
    sender_id = data[-5:-1].hex()
    receiver_id = opt_data[1:5].hex()
    choice_radio_type = data[0]
    user_data = data[1:-5]
    if receiver_id == 'ffffffff': # Broadcast
        if choice_radio_type == _RADIO_TYPE_RPS:
            decode_rps_packet(sender_id, user_data)
        elif choice_radio_type == _RADIO_TYPE_1BS:
            decode_1bs_packet(sender_id, user_data)
        elif choice_radio_type == _RADIO_TYPE_4BS:
            decode_4bs_packet(sender_id, user_data)
        elif choice_radio_type == _RADIO_TYPE_VLD:
            decode_vld_packet(sender_id, user_data)
        else:
            logs.debug('[{}][{}][{}/Not implemented] {}'.format(
                packet_type_format(_PACKET_TYPE_RADIO), device_id_format(sender_id),
                radio_type_format(sender_id, choice_radio_type), user_data.hex()))
    else:
        logs.debug('[{}][{}][{}] {}'.format(
            packet_type_format(_PACKET_TYPE_RADIO),
            device_id_format(sender_id) + ' -> Sent to {} -> Ignoring Unicast Message'.format(receiver_id),
            radio_type_format(sender_id, choice_radio_type), user_data.hex()))

def decode_rps_packet(sender_id: str, user_data: bytes):
    '''
    Decode RADIO > Repeated Switch Communication packets
    '''
    logs.debug('[{}][{}][{}] {}'.format(
        packet_type_format(_PACKET_TYPE_RADIO), device_id_format(sender_id),
        radio_type_format(sender_id, _RADIO_TYPE_RPS), user_data.hex()))

    if is_profile(sender_id, EnoceanProfile.F6_02_01) and len(user_data) == 1:
        data = user_data[0]
        left_bottom = False
        left_top = False
        right_bottom = False
        right_top = False
        pressed = get_bit(data, 3)
        if pressed:
            first_action = (data >> 5) & 0b111
            left_bottom |= (first_action == 0)  # 000
            left_top |= (first_action == 1)     # 001
            right_bottom |= (first_action == 2) # 010
            right_top |= (first_action == 3)    # 011
            if get_bit(data, 7): # 2nd action
                second_action = (data >> 1) & 0b111
                left_bottom |= (second_action == 0)  # 000
                left_top |= (second_action == 1)     # 001
                right_bottom |= (second_action == 2) # 010
                right_top |= (second_action == 3)    # 011
        _dispatch_event(switch_event_handler, sender_id,
            SwitchEvent(pressed, left_bottom, left_top, right_bottom, right_top))

def decode_1bs_packet(sender_id: str, user_data: bytes):
    '''
    Decode RADIO > EnOcean 1 Byte Communication
    '''
    logs.debug('[{}][{}][{}] {}'.format(
        packet_type_format(_PACKET_TYPE_RADIO), device_id_format(sender_id),
        radio_type_format(sender_id, _RADIO_TYPE_1BS), user_data.hex()))

    if len(user_data) == 1:
        is_pairing = not get_bit(user_data[0], 4) # LRN bit for Teach-In (pairing) procedure. Always bit 3 of user_data[0]
        if is_pairing:
            logs.info('From {}: Pairing message'.format(device_id_format(sender_id)))
        else:
            if is_profile(sender_id, EnoceanProfile.D5_00_01):
                contact_closed = get_bit(user_data[0], 7)
                _dispatch_event(contact_event_handler, sender_id, ContactEvent(contact_closed))

def decode_4bs_packet(sender_id: str, user_data: bytes):
    '''
    Decode RADIO > EnOcean 4 Byte Communication
    '''
    logs.debug('[{}][{}][{}] {}'.format(
        packet_type_format(_PACKET_TYPE_RADIO), device_id_format(sender_id),
        radio_type_format(sender_id, _RADIO_TYPE_4BS), user_data.hex()))

    if len(user_data) == 4:
        is_pairing = not get_bit(user_data[3], 4) # LRN bit for Teach-In (pairing) procedure. Always bit 3 of user_data[3]
        if is_pairing:
            logs.info('From {}: Pairing message'.format(device_id_format(sender_id)))
        else:
            temperature = None
            if is_profile(sender_id, EnoceanProfile.A5_02_05):
                # 8-bit, values from 255 (0°C) to 0 (+40°C), step: ~0.15°C
                temperature = ((255 - user_data[2]) / 255) * 40
            elif is_profile(sender_id, EnoceanProfile.A5_02_13):
                # 8-bit, values from 255 (-30°C) to 0 (+50°C), step: ~0.3°C
                temperature = ((255 - user_data[2]) / 255) * 80 - 30
            if temperature:
                _dispatch_event(temperature_event_handler, sender_id,
                    TemperatureEvent(round(temperature, 2)))

def decode_vld_packet(sender_id: str, user_data: bytes):
    '''
    Decode RADIO > Variable Length Data
    '''
    logs.debug('[{}][{}][{}] {}'.format(
        packet_type_format(_PACKET_TYPE_RADIO), device_id_format(sender_id),
        radio_type_format(sender_id, _RADIO_TYPE_VLD), user_data.hex()))

    if is_profile(sender_id, EnoceanProfile.D2_03_0A) and len(user_data) == 2:
        battery_percent = user_data[0]
        action_id = user_data[1]
        single_press = (action_id == 1)
        double_press = (action_id == 2)
        long_press = (action_id == 3)
        release_long = (action_id == 4)
        _dispatch_event(button_event_handler, sender_id,
            ButtonEvent(battery_percent, single_press, double_press, long_press, release_long))

# == Module initialization ==

load_config()
_packet_reading_thread = Thread(target=read_packets, name='Enocean packet reader')
_packet_reading_thread.start()