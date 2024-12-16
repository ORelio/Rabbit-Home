#!/usr/bin/env python3

# =====================================================================
# rfid - monitor nabd rfid events and trigger actions based on tag UIDs
# By ORelio (c) 2023-2024 - CDDL 1.0
# =====================================================================

from configparser import ConfigParser

import actions
import rabbits
import nabd
import scenarios

from logs import logs

config = ConfigParser()
config.read('config/rfid.ini')

_uid_to_action = {}
_name_to_uid = {}
_uid_to_name = {}

for uid in config.sections():
    name = None
    action = None
    for (key, val) in config.items(uid):
        key = key.lower().strip()
        val = val.lower().strip()
        if key == 'name':
            name = val
        if key == 'action':
            action = actions.str2action(val)
    if name is not None:
        if name not in _name_to_uid:
            _name_to_uid[name] = uid
            _uid_to_name[uid] = name
            if action is not None:
                _uid_to_action[uid] = action
            logs.debug('Loaded tag: uid={}, name={}, action={}'.format(uid, name, action))
        else:
            logs.warning('Duplicate tag name, keeping uid={}, skipping uid={}'.format(_name_to_uid[name], uid))
    else:
        logs.warning('Skipping tag without name: {}'.format(uid))

def _nabd_rfid_monitor(rabbit: str, nabd_event: dict):
    '''
    Internal. Callback for monitoring nabd events
    '''
    nabaztag_ip = rabbits.get_ip(rabbit)
    if 'type' in nabd_event and nabd_event['type'] == 'rfid_event':
        if 'event' in nabd_event and nabd_event['event'] == 'detected':
            if 'uid' in nabd_event:
                uid = nabd_event['uid'].lower().replace(':', '')
                name = None
                if uid in _uid_to_name:
                    name = _uid_to_name[uid]
                action = None
                if uid in _uid_to_action:
                    action = _uid_to_action[uid]
                logs.info('Detected tag uid={}, name={}, action={}'.format(uid, name, action))
                if action is not None:
                    logs.debug('Launching action: {}'.format(action))
                    action.run(event_type=scenarios.Event.RFID, rabbit=rabbit)

nabd.event_handler.subscribe(_nabd_rfid_monitor)
