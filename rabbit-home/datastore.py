#!/usr/bin/env python3

# ==================================================
# datastore - store data across application restarts
# By ORelio (c) 2025 - CDDL 1.0
# ==================================================

from threading import Lock

import json
import os

from logs import logs

_DATASTORE_FILE = 'cache/datastore.json'

_datastore = {}
_datastore_lock = Lock()

if os.path.isfile(_DATASTORE_FILE):
    with _datastore_lock:
        with open(_DATASTORE_FILE, 'r') as f:
            try:
                data = json.load(f)
                if isinstance(data, dict):
                    _datastore = data
                else:
                    logs.error('Invalid format for {}, discarding'.format(_DATASTORE_FILE))
            except Exception as e:
                logs.error(e)
                logs.error('Failed to read {}, discarding'.format(_DATASTORE_FILE))

        logs.debug('Loaded datastore:')
        logs.debug(_datastore)
else:
    logs.debug('Starting with empty datastore')

def _save():
    '''
    Save datastore to disk
    '''
    logs.debug('Saving datastore')
    _TMP_FILE = _DATASTORE_FILE + '.tmp'
    with _datastore_lock:
        with open(_TMP_FILE, 'w') as f:
            json.dump(_datastore, f)
        os.remove(_DATASTORE_FILE)
        os.rename(_TMP_FILE, _DATASTORE_FILE)
    logs.debug('Saved datastore')

def get(key: str, default=None):
    '''
    Get saved entry if present, or default value
    '''
    with _datastore_lock:
        return _datastore.get(key, default)

def set(key: str, value):
    '''
    Set entry and save immediately.
    value must be json-serializable.
    Also return the value for convenience
    '''
    logs.debug('Setting entry: {}={}'.format(key, json.dumps(value)))
    with _datastore_lock:
        _datastore[key] = value
    _save()
    return value
