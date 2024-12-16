#!/usr/bin/env python3

# ======================================================================
# event - simple event handling class for subscribing/dispatching events
# By ORelio (c) 2024 - CDDL 1.0
# ======================================================================

from typing import Callable
from threading import Thread, Lock
from logs import logs

import logging

class EventHandler:
    '''
    Represents an Event to which callbacks can be registered.
    When dispatching the events, callbacks are launched on separate threads, with specified arguments.
    log_level: log level for logging when an event occurs. Set log_level to None to disable event logging.
    '''
    def __init__(self, name: str, log_level: int = logging.INFO):
        self._lock = Lock()
        self._callbacks = list()
        self._name = name
        self.log_level = log_level

    def subscribe(self, callback: Callable):
        '''
        Registrer an event handler
        '''
        with self._lock:
            self._callbacks.append(callback)

    def unsubscribe(self, callable: Callable):
        '''
        Unregister an event handler, if present
        '''
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def dispatch(self, *args):
        '''
        Asynchronously call all event handlers with the specified arguments
        '''
        if self.log_level:
            logs.log(self.log_level, '[{}] {}'.format(self._name, str(list(args)).strip('[]')))
        with self._lock:
            for callback in self._callbacks:
                callback_t = Thread(target=callback, args=list(args), name='Event callback')
                callback_t.start()
