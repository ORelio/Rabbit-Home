#!/usr/bin/env python3

# ===========================================
# alarm - home remote monitoring and alerting
# By ORelio (c) 2025-2026 - CDDL 1.0
# ===========================================

from flask import Blueprint, jsonify, request
from threading import Thread, Lock
from configparser import ConfigParser
from enum import Enum

import time

from logs import logs
from openings import OpenState

import cameras
import datastore
import motion
import notifications
import openings
import rabbits
import lights

_command_lock = Lock()

_keycode = None

_typed = ''
_typed_time = 0
_typed_attempts = 0

_KEYPAD_MAX_ATTEMPTS = 3
_KEYPAD_TIMEOUT_SECONDS = 30
_FRONT_DOOR_GRACE_TIME_SECONDS = 30
_ENABLE_GRACE_TIME_SECONDS = 75

assert(_FRONT_DOOR_GRACE_TIME_SECONDS < _ENABLE_GRACE_TIME_SECONDS)

_rabbit = None
_notification_topic = None

class EnableStatus(Enum):
    GRACE = 1
    READY = 2
    PREALARM = 3
    ALARM = 4

_instance_lock = Lock()
_instance_token = 0
_instance_status = EnableStatus.READY
_DATASTORE_ALARM_ENABLED = 'alarm.enabled'

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
                # Ignore button presses if no keycode provided
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
                        openings_not_closed = list()
                        for opening in openings.get_all():
                            logs.info('Opening {}: {}'.format(opening, openings.get_current_state(opening)))
                            if not openings.is_front_door(opening) and openings.get_current_state(opening) != OpenState.CLOSED:
                                openings_not_closed.append(opening)
                        if len(openings_not_closed) > 0:
                            logs.info('Tried to enable alarm using valid PIN code, but there are non-closed opening(s): {}'.format(', '.join(openings_not_closed)))
                            if len(openings_not_closed) > 1:
                                notifications.publish(
                                    title="Portes ou fenêtres ouvertes",
                                    message = "Pour activer l'alarme, manœuvrer les portes ou fenêtres pour s'assurer qu'elles sont fermées : {}".format(', '.join(openings_not_closed)),
                                    tags='door,window,warning',
                                    topic=_notification_topic,
                                    priority=notifications.Priority.HIGH,
                                )
                            else:
                                notifications.publish(
                                    title="Porte ou fenêtre ouverte",
                                    message = "Pour activer l'alarme, manœuvrer la porte ou fenêtre pour s'assurer qu'elle est fermée : {}".format(openings_not_closed[0]),
                                    tags='door,window,warning',
                                    topic=_notification_topic,
                                    priority=notifications.Priority.HIGH,
                                )
                        else:
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

def _grace_timeout_thread(thread_token):
    '''
    Enable alarm (thread for grace time)
    '''
    global _instance_status
    time.sleep(_ENABLE_GRACE_TIME_SECONDS)
    with _instance_lock:
        if thread_token == _instance_token and is_enabled() and _instance_status == EnableStatus.GRACE:
            _instance_status = EnableStatus.READY

def _enable_alarm(with_grace_time: bool = True):
    '''
    Enable the alarm (internal, after using keycode)
    '''
    global _instance_token
    global _instance_status
    with _instance_lock:
        _instance_token = time.time()
        if with_grace_time:
            _instance_status = EnableStatus.GRACE
            Thread(target=_grace_timeout_thread, args=[_instance_token], name='Alarm grace timeout').start()
        else:
            _instance_status = EnableStatus.READY
        datastore.set(_DATASTORE_ALARM_ENABLED, True)
        cameras.start_monitoring()

def _disable_alarm():
    '''
    Disable the alarm (internal, after using keycode)
    '''
    global _instance_token
    global _instance_status
    with _instance_lock:
        _instance_token = 0
        _instance_status = EnableStatus.READY
        datastore.set(_DATASTORE_ALARM_ENABLED, False)
        cameras.stop_monitoring()
        # TODO turn off alarm bell

def _alarm_bell_and_lights():
    '''
     Child thread for _triggered_alarm_thread
    '''
    # TODO turn on alarm bell
    for light in lights.get_all():
        lights.switch(light, on=True)

def _triggered_alarm_thread(thread_token):
    '''
    Initialize triggered alarm (thread)
    '''
    global _instance_status

    if _instance_status == EnableStatus.PREALARM:
        logs.info('Entered prealarm grace delay')
        notifications.publish(
            title="Quelqu'un est entré",
            message="L'alarme va bientôt se déclencher",
            tags='door,stopwatch',
            topic=_notification_topic,
        )
        time.sleep(_FRONT_DOOR_GRACE_TIME_SECONDS)

    with _instance_lock:
        if thread_token == _instance_token and is_enabled():
            _instance_status = EnableStatus.ALARM
        else:
            return # Alarm disabled during grace time

    logs.info('Starting alarm')
    notifications.publish(
        title='Alarme déclenchée',
        message='Attention immédiate requise',
        tags='rotating_light,loud_sound',
        topic=_notification_topic,
        priority=notifications.Priority.HIGHEST
    )

    # Asynchronously turn on bell and lights, need to take the first photo ASAP
    Thread(target=_alarm_bell_and_lights, name='Triggered Alarm - Bell and Lights').start()

    # Take photos with cameras as long as alarm is triggered
    while thread_token == _instance_token and is_enabled():
        for camera in cameras.get_all():
            cameras.capture_and_send(
                camera=camera,
                title="Alarme déclenchée",
                message=camera,
                tags='rotating_light,video_camera',
                priority=notifications.Priority.LOWEST,
                synchronous=True,
            )

def _trigger_alarm(with_prealarm: bool = False):
    '''
    Trigger the alarm
    '''
    global _instance_status
    with _instance_lock:
        if _instance_status in [ EnableStatus.PREALARM, EnableStatus.ALARM ]:
            return # sensor callback trying to enable alarm twice, may happen in case of race condition
        _instance_status = EnableStatus.PREALARM if with_prealarm else EnableStatus.ALARM
        Thread(target=_triggered_alarm_thread, args=[_instance_token], name='Triggered Alarm').start()

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

    if _instance_status != EnableStatus.READY:
        logs.debug('Door/Window "{}" opened but alarm is not in READY state: (), ignoring'.format(opening_name, _instance_status))
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
        _trigger_alarm(with_prealarm=True)
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

def _motion_event_callback(motion_event: motion.MotionEvent):
    '''
    Callback for motion sensor events
    '''
    if motion_event.outside:
        logs.debug('Motion detected by sensor "{}" but sensor is located outside, ignoring'.format(motion_event.sensor))
        return

    if not is_enabled():
        logs.debug('Motion detected by sensor "{}" but alarm is disabled, ignoring'.format(motion_event.sensor))
        return

    if _instance_status != EnableStatus.READY:
        logs.debug('Motion detected by sensor "{}" but alarm is not in READY state: (), ignoring'.format(motion_event.sensor, _instance_status))
        return

    logs.warning('Motion detected by sensor "{}" after activating the alarm, triggering now'.format(motion_event.sensor))
    notifications.publish(
        title="Mouvement détecté",
        message="Le capteur {} s'est déclenché".format(motion_event.sensor),
        tags='rotating_light,trackball',
        topic=_notification_topic,
        priority=notifications.Priority.HIGHEST,
    )
    _trigger_alarm()

motion.event_handler.subscribe(_motion_event_callback)

if is_enabled():
    logs.warning('Alarm was enabled before shutting down service, reenabling')
    notifications.publish(
        title="Réactivation de l'alarme",
        message='Reprise sur coupure de courant',
        tags='recycle',
        topic=_notification_topic
    )
    _enable_alarm(with_grace_time=False)

# === HTTP API ===

alarm_api = Blueprint('alarm_api', __name__)

@alarm_api.route('/api/v1/alarm', methods = ['GET'])
def alarm_api_get():
    return jsonify({'enabled': is_enabled(), 'detail': 'DISABLED' if not is_enabled() else '{}'.format(_instance_status.name)})

@alarm_api.route('/api/v1/alarm/toggle', methods = ['POST'])
def alarm_api_toggle():
    reqdata = request.get_json()
    if reqdata and 'code' in reqdata:
        for c in reqdata['code']:
            if c in '1234567890':
                command(c)
            else:
                return jsonify({'error': 'invalid code'})
        if is_enabled():
            command('OFF')
        else:
            command('ON')
        return jsonify({'message': 'request submitted'})
    return jsonify({'error': 'missing code'})
