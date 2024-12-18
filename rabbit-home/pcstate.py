#!/usr/bin/env python3

# =====================================================================================================
# pcstate - map startup/logon/logoff/shutdown events to actions, from a PC running System State Webhook
# https://github.com/ORelio/System-State-Webhook/
# By ORelio (c) 2024 - CDDL 1.0
# =====================================================================================================

from flask import Blueprint
from configparser import ConfigParser
from threading import Thread, Lock
from enum import Enum

import actions
import rabbits
import scenarios

from logs import logs
from events import EventHandler

class PcState(Enum):
    ACTIVE = 1,
    LOCKED = 2,
    OFF = 3,
    UNKNOWN = 4,

_pc_actions = {}
_pc_rabbits = {}
_pc_states = {}
_pc_states_lock = Lock()

_valid_states = ['startup', 'logon', 'logoff', 'shutdown']

config = ConfigParser()
config.read('config/pcstate.ini')

for section_name in config.sections():
    pc = section_name.lower()
    rabbit = None
    if pc in _pc_actions:
        raise ValueError('Duplicate PC name: "{}"'.format(pc))
    _pc_actions[pc] = dict()
    for (field, val) in config.items(section_name):
        if field == 'rabbit':
            rabbit = rabbits.get_name(val)
            _pc_rabbits[pc] = rabbit
        elif field in _valid_states:
            _pc_actions[pc][field] = actions.str2action(val, setting_name='{}/{}'.format(pc, field))
        else:
            raise ValueError('Unknown config option "{}", expecting {}'.format(field, 'rabbit|' + '|'.join(_valid_states)))
    logs.debug('Loaded PC (name="{}", rabbit="{}"):'.format(pc, rabbit))
    for action in _pc_actions[pc]:
        logs.debug('[{}/{}] {}'.format(pc, action, _pc_actions[pc][action]))

'''
PcState Event Handler
Callbacks will receive args = computer: str, state: PcState, rabbit: str
'''
event_handler = EventHandler('PC State')

def pc_state_change(computer: str, state: str):
    '''
    Callback from rabbit-home.py/pc_state API
    '''
    rabbit_name = get_rabbit(computer)
    with _pc_states_lock:
        if state == 'logon' or state == 'startup':
            _pc_states[pc] = PcState.ACTIVE
        elif state == 'logoff':
            _pc_states[pc] = PcState.LOCKED
        elif state == 'shutdown':
            _pc_states[pc] = PcState.OFF
        event_handler.dispatch(computer, _pc_states[pc], rabbit_name)
    if state in _pc_actions[pc]:
        _pc_actions[pc][state].run(event_type=scenarios.Event.PC_STATE, rabbit=rabbit_name)

'''
PcState API for webhook client to submit new states
'''
pcstate_api = Blueprint('pc_state_api', __name__)

@pcstate_api.route('/api/v1/pcstate/<computer>/<state>', methods = ['GET'])
def pcstate_api_webhook(computer, state):
    '''
    Receive new PC state event from webhook client
    '''
    if computer and state:
        computer = computer.lower()
        state = state.lower()
        if computer in _pc_actions:
            if state in _valid_states:
                process_t = Thread(target=pc_state_change, args=[computer, state], name='PC State Change')
                process_t.start()
                return 'OK', 200
            else:
                logs.warning('Ignoring API call with unknown state: {}'.format(state))
        else:
            logs.warning('Ignoring API call for unknown computer: {}'.format(computer))
    else:
        logs.warning('Got invalid API call, computer="{}", state="{}"'.format(computer, state))
    return 'Invalid request', 400

def get_state(computer: str) -> PcState:
    '''
    Get current computer state
    '''
    with _pc_states_lock:
        return _pc_states.get(computer.lower(), PcState.UNKNOWN)

def get_rabbit(computer: str) -> str:
    '''
    Get rabbit for computer
    '''
    return _pc_rabbits.get(computer.lower(), None)
