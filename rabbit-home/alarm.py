#!/usr/bin/env python3

# ===========================================
# alarm - home remote monitoring and alerting
# By ORelio (c) 2025 - CDDL 1.0
# ===========================================

from configparser import ConfigParser

import time

from logs import logs
from openings import OpenState

import cameras
import datastore
import notifications
import openings
import rabbits

_keycode = None
_typed = ''
_rabbit = None
_notification_topic = None

_DATASTORE_ALARM_ENABLED = 'alarm.enabled'
_enable_time = 0

config = ConfigParser()
config.read('config/alarm.ini')
_keycode = config.get('Alarm', 'Keycode')
if len(str(_keycode)) < 6:
    raise ValueError('Keycode too short, minimum 6 characters')
for c in _keycode:
    if not c in '0123456789':
        raise ValueError('Invalid keycode digit: {}'.format(c))
_rabbit = rabbits.get_name(config.get('Alarm', 'Rabbit'))
_notification_topic = config.get('Alarm', 'Channel')

def command(cmd: str):
    '''
    Handle button press: Keypad, ON/OFF
    cmd: ON/OFF or a digit (as string)
    '''
    global _typed
    cmd = cmd.upper()
    if not cmd in ['ON', 'OFF', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9' ]:
        raise ValueError('Invalid command: {}'.format(char))
    if cmd == 'ON' or cmd == 'OFF':
        if _typed != _keycode:
            logs.info('Tried to enable or disable alarm but wrong keycode')
            # TODO Play sound using rabbit
        else:
            desired_state = (cmd == 'ON')
            if is_enabled() == desired_state:
                logs.info('Tried to enable or disable alarm but already in desired state')
            else:
                if desired_state:
                    logs.info('Enabling alarm')
                    notifications.publish('Après saisie du code PIN', title="Alarme activée", tags='green_circle,lock', topic=_notification_topic)
                    _enable_alarm()
                    # TODO Play sound using rabbit
                else:
                    logs.info('Disabling alarm')
                    notifications.publish('Après saisie du code PIN', title="Alarme désactivée", tags='red_circle,unlock', topic=_notification_topic)
                    _disable_alarm()
                    # TODO Play sound using rabbit
        _typed = ''
    else:
        _typed = _typed + cmd
        if len(_typed) > len(_keycode):
            _typed = _typed[-1 * len(_keycode):]

def is_enabled() -> bool:
    '''
    Determine whether the alarm is enabled
    '''
    return datastore.get(_DATASTORE_ALARM_ENABLED, False)

def _enable_alarm(enable_time: int = 0):
    '''
    Operations for enabling alarm
    enable_time: Set custom enable time, default is current timestamp
    '''
    global _enable_time
    if enable_time <= 0:
        enable_time = time.time()
    _enable_time = enable_time
    datastore.set(_DATASTORE_ALARM_ENABLED, True)
    cameras.start_monitoring(topic=_notification_topic)

def _disable_alarm():
    '''
    Operaitons for disabling alarm
    '''
    datastore.set(_DATASTORE_ALARM_ENABLED, False)
    cameras.stop_monitoring(topic=_notification_topic)

def _trigger_alarm():
    '''
    Trigger the alarm
    '''
    # TODO add alarm bell
    for camera in cameras.get_all():
        cameras.capture_and_send(
            camera=camera,
            message="Alarme déclenchée",
            tags='rotating_light,video_camera',
            priority_first=notifications.Priority.HIGHEST,
            priority=notifications.Priority.LOWEST,
            count=10
        )

def _opening_event_callback(opening_name: str, state: OpenState, shutter_name: str = None, rabbit_name: str = None, is_front_door: bool = False):
    '''
    Callback for door or windows opened or closed
    '''
    if state != OpenState.OPEN:
        logs.debug('Door/Window "{}" changed to non-open state {}, ignoring'.format(opening_name, state))
        return

    if not is_enabled():
        logs.debug('Door/Window "{}" opened but alarm is disabled, ignoring'.format(opening_name))
        return

    if _enable_time + 75 >= time.time():
        logs.debug('Door/Window "{}" opened quickly after activating alarm, ignoring'.format(opening_name))
        return

    if is_front_door:
        logs.info('Front door opened after activating the alarm, triggering after a grace delay')
        cameras.capture_and_send(
            camera='entree',
            message="Quelqu'un est entré",
            tags='detective,video_camera',
            priority_first=notifications.Priority.NORMAL,
            priority=notifications.Priority.LOWEST,
            count=10
        )
        time.sleep(30)
        if is_enabled():
            logs.warning('Alarm not disabled during grace delay, triggering now')
            _trigger_alarm()
    else:
        logs.warning('Other Door/Window opened after activating the alarm, triggering now')
        notifications.publish("Le capteur {} s'est déclenché".format(opening_name), title="Ouverture détectée", tags='rotating_light,window', topic=_notification_topic, priority=notifications.Priority.HIGHEST)
        _trigger_alarm()

openings.event_handler.subscribe(_opening_event_callback)

if is_enabled():
    logs.warning('Alarm was enabled before shutting down service, reenabling')
    notifications.publish('Reprise sur coupure de courant', title="Réactivation de l'alarme", tags='recycle', topic=_notification_topic)
    _enable_alarm(time.time() - 75)
