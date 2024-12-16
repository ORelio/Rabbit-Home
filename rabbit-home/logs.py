#!/usr/bin/env python3

# ==========================================
# logs - handle logs and generate logs files
# By ORelio (c) 2024 - CDDL 1.0
# ==========================================

import sys
import logging
import threading

from configparser import ConfigParser

# Logging configuration

config = ConfigParser()
config.read('config/logs.ini')
file_name = config.get('Logs', 'File', fallback=None)
log_level = config.get('Logs', 'Level').upper()

# Initialize logging file

logs = logging.getLogger('rabbithome')
log_level = getattr(logging, log_level.upper())
log_format = '[%(asctime)s] [%(levelname)s] [%(filename)s] %(message)s'

if file_name and len(file_name) > 0:
    logging.basicConfig(filename=file_name, level=log_level, format=log_format)
    # Also log to console in addition to log file
    _ch = logging.StreamHandler()
    _ch.setLevel(log_level)
    formatter = logging.Formatter(log_format)
    _ch.setFormatter(formatter)
    logs.addHandler(_ch)
else:
    logging.basicConfig(level=log_level, format=log_format)

# Warning for missing log file

if file_name is None or len(file_name) < 1:
    logs.warning('Log file not set in config, logs will only show in console')

# Log uncaught exceptions

def exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logs.critical('Uncaught exception', exc_info=(exc_type, exc_value, exc_traceback))
sys.excepthook = exception_handler

# Log uncaught exceptions from threads

def thread_exception_handler(exc_data):
    exc_type, exc_value, exc_traceback, thread = exc_data
    logs.critical('Uncaught exception in thread "{}"'.format(thread.name), exc_info=(exc_type, exc_value, exc_traceback))
threading.excepthook = thread_exception_handler

# == Usage ==
# from logs import logs
# logs.debug() / logs.info(), logs.warning(), logs.error(), logs.critical()
