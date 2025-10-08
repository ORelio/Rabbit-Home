#!/usr/bin/env python3

# ===========================================
# alarm - home remote monitoring and alerting
# By ORelio (c) 2025 - CDDL 1.0
# ===========================================

from threading import Thread, Lock
from configparser import ConfigParser

import time

from logs import logs
from openings import OpenState

import cameras
import datastore
import notifications
import openings
import rabbits

_command_lock = Lock()

_keycode = None

_typed = ''
_typed_time = 0
_typed_attempts = 0

_KEYPAD_MAX_ATTEMPTS = 3
_KEYPAD_TIMEOUT_SECONDS = 30
_FRONT_DOOR_GRACE_TIME_SECONDS = 30
_ENABLE_GRACE_TIME_SECONDS = 75

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
    global _typed_time
    global _typed_attempts
    cmd = cmd.upper()
    if not cmd in ['ON', 'OFF', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9' ]:
        raise ValueError('Invalid command: {}'.format(char))
    with _command_lock:
        if _typed_time + _KEYPAD_TIMEOUT_SECONDS < time.time():
            # Reset Keypad and Attempts on idle timeout
            _typed = ''
            _typed_attempts = 0
        if cmd == 'ON' or cmd == 'OFF':
            if len(_typed) == 0:
                # Ignore button presses if not keycode provided
                logs.info('Tried to enable or disable alarm but no keycode typed')
            else:
                # Reject ON/OFF attempts on too many incorrect PINs
                if _typed_attempts >= _KEYPAD_MAX_ATTEMPTS:
                    logs.info('Tried to enable or disable alarm but too many attempts, wait {} seconds'.format(_KEYPAD_TIMEOUT_SECONDS))
                    notifications.publish(
                        title="Code PIN bloqué",
                        message='Un mauvais code a été saisi précédemment, attendre {} secondes'.format(_KEYPAD_TIMEOUT_SECONDS),
                        tags='no_entry,lock',
                        topic=_notification_topic,
                        priority=notifications.Priority.HIGH,
                    )
                    # TODO Play long deny sound
                elif _typed != _keycode:
                    _typed_attempts += 1
                    _typed_time = time.time()
                    logs.info('Tried to enable or disable alarm but wrong keycode. Attempt {}/{}'.format(_typed_attempts, _KEYPAD_MAX_ATTEMPTS))
                    if _typed_attempts < 3:
                        notifications.publish(
                            title="Code PIN incorrect",
                            message='Un mauvais code a été saisi ({}/{})'.format(_typed_attempts, _KEYPAD_MAX_ATTEMPTS),
                            tags='x,lock',
                            topic=_notification_topic,
                            priority=notifications.Priority.HIGH,
                        )
                        # TODO Play deny sound
                    else:
                        notifications.publish(
                            title="Code PIN bloqué",
                            message='Un mauvais code a été saisi ({}/{})\nAttendre {} secondes'.format(_typed_attempts, _KEYPAD_MAX_ATTEMPTS, _KEYPAD_TIMEOUT_SECONDS),
                            tags='no_entry,lock',
                            topic=_notification_topic,
                            priority=notifications.Priority.HIGHEST,
                        )
                        # TODO Play long deny sound
                else:
                    desired_state = (cmd == 'ON')
                    if is_enabled() == desired_state:
                        logs.info('Tried to {} alarm but already in desired state'.format('enable' if desired_state else 'disable'))
                        notifications.publish(
                            title='Code PIN valide',
                            message="Alarme déjà {}".format('activée' if desired_state else 'désactivée'),
                            tags='information_source,{}'.format('lock' if desired_state else 'unlock'),
                            topic=_notification_topic,
                        )
                        # TODO Play enable or disable sound
                    elif desired_state:
                        logs.info('Enabling alarm using valid PIN code')
                        notifications.publish(
                            title="Alarme activée",
                            message='Après saisie du code PIN',
                            tags='green_circle,lock',
                            topic=_notification_topic,
                        )
                        _enable_alarm()
                        # TODO Play enable sound
                    else:
                        logs.info('Disabling alarm using valid PIN code')
                        notifications.publish(
                            title="Alarme désactivée",
                            message='Après saisie du code PIN',
                            tags='red_circle,unlock',
                            topic=_notification_topic,
                        )
                        _disable_alarm()
                        # TODO Play disable sound
                    # Reset attempts after successful action
                    _typed_attempts = 0
                # Reset typed code regardless of success
                _typed = ''
        else:
            _typed_time = time.time()
            _typed = _typed + cmd
            if len(_typed) > len(_keycode):
                _typed = _typed[-1 * len(_keycode):]
            logs.debug('Typed keycode: {}'.format(_typed))

def is_enabled() -> bool:
    '''
    Determine whether the alarm is enabled
    '''
    return datastore.get(_DATASTORE_ALARM_ENABLED, False)

def _enable_alarm(with_grace_time: bool = True):
    '''
    Operations for enabling alarm
    '''
    global _enable_time
    if with_grace_time:
        _enable_time = time.time()
    else:
        _enable_time = time.time() - _ENABLE_GRACE_TIME_SECONDS - 1
    datastore.set(_DATASTORE_ALARM_ENABLED, True)
    cameras.start_monitoring()

def _disable_alarm():
    '''
    Operations for disabling alarm
    '''
    datastore.set(_DATASTORE_ALARM_ENABLED, False)
    cameras.stop_monitoring()

def _trigger_alarm_thread():
    '''
    Trigger the alarm (underlying thread)
    '''
    # TODO ring alarm bell
    priority = notifications.Priority.HIGHEST
    while is_enabled():
        for camera in cameras.get_all():
            cameras.capture_and_send(
                camera=camera,
                title="Alarme déclenchée",
                message=camera,
                tags='rotating_light,video_camera',
                priority=priority,
                synchronous=True,
            )
        priority = notifications.Priority.LOWEST

def _trigger_alarm():
    '''
    Trigger the alarm
    '''
    Thread(target=_trigger_alarm_thread, name='Triggered Alarm').start()

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

    if _enable_time + _ENABLE_GRACE_TIME_SECONDS >= time.time():
        logs.debug('Door/Window "{}" opened quickly after activating alarm, ignoring'.format(opening_name))
        return

    if is_front_door:
        logs.info('Front door opened and alarm enabled, taking photos and triggering after a grace delay')
        cameras.capture_and_send(
            camera='entree',
            message="Quelqu'un est entré",
            tags='detective,video_camera',
            priority_first=notifications.Priority.NORMAL,
            priority=notifications.Priority.LOWEST,
            count=10
        )
        enable_time_before_waiting = _enable_time # If enable time change, this means the alarm was reset
        # TODO play warning sound(s)
        time.sleep(_FRONT_DOOR_GRACE_TIME_SECONDS)
        if is_enabled() and _enable_time == enable_time_before_waiting: # still enabled and not reset
            logs.warning('Alarm not disabled during grace delay, triggering now')
            _trigger_alarm()
    else:
        logs.warning('Other Door/Window opened after activating the alarm, triggering now')
        notifications.publish(
            title="Ouverture détectée",
            message="Le capteur {} s'est déclenché".format(opening_name),
            tags='rotating_light,window',
            topic=_notification_topic,
            priority=notifications.Priority.HIGHEST,
        )
        _trigger_alarm()

openings.event_handler.subscribe(_opening_event_callback)

if is_enabled():
    logs.warning('Alarm was enabled before shutting down service, reenabling')
    notifications.publish(
        title="Réactivation de l'alarme",
        message='Reprise sur coupure de courant',
        tags='recycle',
        topic=_notification_topic
    )
    _enable_alarm(with_grace_time=False)
