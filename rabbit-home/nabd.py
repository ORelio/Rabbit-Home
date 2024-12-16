#!/usr/bin/env python3

# =============================================================================================
# nabd - remotely connect and interact with the nabd daemon over SSH (Nabaztag/tag:tag:tag)
# nabd allows launching animations (ears, leds, sounds) and watching RFID and microphone events
# https://github.com/nabaztag2018/pynab/blob/master/PROTOCOL.md
# By ORelio (c) 2023-2024 - CDDL 1.0
# =============================================================================================

from threading import Thread, Lock
from typing import Callable, Union

import shutil
import subprocess
import signal
import json
import time
import logging

import rabbits

from events import EventHandler
from logs import logs

_subprocess_lock = Lock()
_threads = dict()
_subprocesses = dict()

'''
Nabd Event Handler
Callbacks will receive args = rabbit: str, event_json: dict
'''
event_handler = EventHandler('Nabd', log_level=logging.DEBUG)

def connect(rabbit: str, rotate_ears: bool = True):
    '''
    Connect to nabaztag nabd daemon over SSH in a background thread.
    Note that SSH public key authentication must be configured, 'ssh pi@na.baz.tag.ip' must give a shell on the nabaztag.
    '''
    nabaztag_ip = rabbits.get_ip(rabbit)
    with _subprocess_lock:
        if nabaztag_ip not in _threads or not _threads[nabaztag_ip].is_alive():
            t = Thread(target=_ssh_connect_and_read, args=[nabaztag_ip], name='Nabd SSH session')
            t.start()
            _threads[nabaztag_ip] = t

    # Rotate ears to show successful connection
    if rotate_ears:
        publish(nabaztag_ip, [
            {"type":"ears", "left": 1, "right": 1},
            {"type":"ears", "left": 0, "right": 0}
        ])

def publish(rabbit: str, message: Union[dict, list[dict]]):
    '''
    Push one or several nabd messages to the specified Nabaztag IP. Will automatically connect if not already connected.
    Note that if everything goes well, published messages will come back and be dispatched to subscribers.
    '''
    nabaztag_ip = rabbits.get_ip(rabbit)
    logs.debug('Sending to {}: {}'.format(rabbits.get_name(rabbit), message))
    if isinstance(message, dict):
        message = [message]
    _ssh_write(nabaztag_ip, message)

def _ssh_connect_and_read(rabbit: str):
    '''
    Internal. Connect to remote nabd process over SSH and start monitoring
    '''
    nabaztag_ip = rabbits.get_ip(rabbit)
    while True:
        if nabaztag_ip != '127.0.0.1':
            # Connect to nabd over SSH (service installed on a different system, the local system must have an ssh key authorized on the nabaztag)
            nabd_process = subprocess.Popen([shutil.which('ssh'), '-T', 'pi@' + nabaztag_ip, 'nc -4 localhost 10543'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        else:
            # Connect to nabd locally (service installed directly on the nabaztag)
            nabd_process = subprocess.Popen([shutil.which('nc'), '-4', 'localhost', '10543'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

        # Make subprocess available to other threads for writing to stdin
        with _subprocess_lock:
            _subprocesses[nabaztag_ip] = nabd_process

        # Subscribe to all idle events after connecting to nabd
        publish(nabaztag_ip, [
            {"type":"mode", "mode":"idle", "events":["asr/*", "button", "ears", "rfid/*"]}
        ])

        # Read messages coming from nabd
        while True:
            outlst = []
            reader_t = Thread(target=_ssh_read, args=[nabd_process, outlst], name='Nabd SSH readline')
            reader_t.start()
            reader_t.join(15)

            # Make sure SSH session is still alive, sending keepalives when unsure
            # Thread should read a message and exit, thread still alive means no message from nabd yet
            if reader_t.is_alive():
                publish(nabaztag_ip, {"type":"gestalt"})
                reader_t.join(15)
                if reader_t.is_alive():
                    # At this point, a message should have been received in response to "gestalt" command
                    # Thread still alive means no message back from nabd: assume connection lost
                    nabd_process.kill()
                    break
            if len(outlst) == 0 or len(outlst[0]) == 0:
                nabd_process.kill()
                break

            # Process message coming from nabd
            nabd_message = json.loads(outlst[0].decode('utf-8').strip())
            event_handler.dispatch(rabbits.get_name(nabaztag_ip), nabd_message)

        # Connection lost
        with _subprocess_lock:
            _subprocesses[nabaztag_ip] = None
        event_handler.dispatch(rabbits.get_name(nabaztag_ip), {'type': 'state', 'state': 'offline'})
        time.sleep(1)

def _ssh_read(nabd_process: subprocess.Popen, outlst: list):
    '''
    Internal. Read a line from subprocess, store it in outlst and return. For use in separate thread.
    '''
    outlst.append(nabd_process.stdout.readline())

def _ssh_write(rabbit: str, nabd_messages: list[dict]):
    '''
    Internal. Send Nabd messages through nabd session
    '''
    # Make sure we are connected to the Nabaztag
    nabaztag_ip = rabbits.get_ip(rabbit)
    connect(nabaztag_ip, rotate_ears=False)

    # Get/Wait for subprocess to spawn
    nabd = None
    got_subprocess = False
    while not got_subprocess:
        with _subprocess_lock:
            if nabaztag_ip in _subprocesses:
                nabd = _subprocesses[nabaztag_ip]
        if nabd is not None and nabd.poll() is None:
            got_subprocess = True
        else:
            time.sleep(0.1)

    # Send message through subprocess
    # We could have one lock per subprocess but let's keep it simple,
    # there won't be many rabbits to handle anyway
    with _subprocess_lock:
        for msg in nabd_messages:
            nabd.stdin.write(bytes(json.dumps(msg) + '\r\n', 'utf-8'))
        nabd.stdin.flush()
