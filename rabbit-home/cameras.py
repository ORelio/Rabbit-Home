#!/usr/bin/env python3

# =============================
# cameras - manage RTSP cameras
# By ORelio (c) 2025 - CDDL 1.0
# =============================

from threading import Thread, Lock
from configparser import ConfigParser
from datetime import datetime

import cv2
import time

from logs import logs

import notifications
import plugs433
import requests

_cameras = []
_camera_locks = {}
_camera_should_monitor = {}
_camera_thread_token = {}

_TOKEN_INACTIVE = 0

_camera_ip = {}
_camera_port = {}
_camera_stream = {}
_camera_stream_low_def = {}
_camera_rtsp_accesskey = {}
_camera_screenshot_frequency_minutes = {}
_camera_power_socket = {}

_DEFAULT_RTSP_PORT = 554

config = ConfigParser()
config.read('config/cameras.ini')

# Load configuration file
for camera_name_raw in config.sections():
    camera_name = camera_name_raw.lower()
    if camera_name in _cameras:
        raise ValueError('Duplicate camera name: {}'.format(camera_name_raw))
    camera_ip = config.get(camera_name_raw, 'IP')
    camera_port = config.getint(camera_name_raw, 'Port', fallback=_DEFAULT_RTSP_PORT)
    camera_stream = config.get(camera_name_raw, 'Stream')
    camera_stream_low_def = config.get(camera_name_raw, 'StreamLowDef', fallback=None)
    rtsp_login = config.get(camera_name_raw, 'RtspLogin', fallback=None)
    rtsp_pass = config.get(camera_name_raw, 'RtspPass', fallback=None)
    if rtsp_login and not rtsp_pass or rtsp_pass and not rtsp_login:
        raise ValueError('Must specify both RTSP login and pass for camera: {}'.format(camera_name_raw))
    camera_rtsp_accesskey = None
    if rtsp_login and rtsp_pass:
        camera_rtsp_accesskey = '{}:{}'.format(rtsp_login, rtsp_pass)
    camera_screenshot_frequency_minutes = config.getint(camera_name_raw, 'AutoScreenFrequMinutes', fallback=0)
    if camera_screenshot_frequency_minutes < 0:
        camera_screenshot_frequency_minutes = 0
    camera_power_socket = config.get(camera_name_raw, 'PowerSocket', fallback=None)
    _cameras.append(camera_name)
    _camera_locks[camera_name] = Lock()
    _camera_should_monitor[camera_name] = False
    _camera_thread_token[camera_name] = _TOKEN_INACTIVE
    _camera_ip[camera_name] = camera_ip
    _camera_port[camera_name] = camera_port
    _camera_stream[camera_name] = camera_stream
    _camera_stream_low_def[camera_name] = camera_stream_low_def
    _camera_rtsp_accesskey[camera_name] = camera_rtsp_accesskey
    _camera_screenshot_frequency_minutes[camera_name] = camera_screenshot_frequency_minutes
    _camera_power_socket[camera_name] = camera_power_socket
    logs.debug(('Loaded camera "{}" (IP={}, Port={}, Stream={}, StreamLowDef={}, Account={}, '
        + 'ScreenshotFrequency={}min, PowerSocket={})').format(
            camera_name,
            camera_ip,
            camera_port,
            camera_stream,
            camera_stream_low_def,
            rtsp_login,
            camera_screenshot_frequency_minutes,
            camera_power_socket
    ))
logs.debug('Loaded {} camera definitions'.format(len(_cameras)))

def get_all() -> list:
    '''
    Get all cameras
    '''
    return _cameras

def _get_host(camera: str) -> str:
    '''
    Get ip:port from camera name
    '''
    camera = camera.lower()
    if not camera in _cameras:
        raise ValueError('Unknown camera: {}'.format(camera))
    return '{}:{}'.format(_camera_ip[camera], _camera_port[camera])

def _param_to_camera_list(camera: str = None) -> list:
    '''
    Convert param to list of cameras (internal)
    '''
    cameras = _cameras
    if camera:
        cameras = [camera]
    return cameras

def _switch_camera_socket(on: bool, camera: str = None):
    '''
    Switch cameras ON or OFF
    on: Desired ON/OFF state, True means ON, False means OFF
    camera: Name of camera to switch (default: all cameras)
    '''
    cameras = _param_to_camera_list(camera)
    logs.debug('Switching camera{} {}: {}'.format(
        's' if len(cameras) > 1 else '',
        'ON' if on else 'OFF',
        ', '.join(cameras)))
    for camera in cameras:
        socket = _camera_power_socket[camera]
        if not socket:
            raise ValueError('No socket configured for camera "{}" so cannot switch ON/OFF'.format(camera))
        plugs433.switch(socket, on)

def is_reachable(camera: str, timeout_seconds: int = 10) -> bool:
    '''
    Check if the specified camera is up and running
    '''
    host = _get_host(camera)
    if timeout_seconds < 5:
        raise ValueError('Timeout too short, minimum 5 seconds')
    try:
        requests.options('http://{}/'.format(host), timeout=timeout_seconds)
    except requests.exceptions.ConnectionError as e:
        if len(e.args) > 0 \
          and len(e.args[0].args) > 1 \
          and str(e.args[0].args[1]).strip() == 'RTSP/1.0 200 OK':
            return True
    return False

def wait_for_camera(camera: str, timeout_seconds = 120) -> bool:
    '''
    Wait for camera to be up and running.
    Returns TRUE if the camera is up and running, FALSE for timeout
    '''
    if timeout_seconds < 10:
        raise ValueError('Timeout too short, minimum 10 seconds')
    request_count = timeout_seconds / 10
    while request_count > 0:
        request_count -= 1
        time_start = time.time()
        if is_reachable(camera, timeout_seconds=10):
            return True
        time_elapsed = time.time() - time_start
        if time_elapsed < 10:
            time.sleep(10 - time_elapsed)
    return False

def _capture_error(camera, topic, message_format):
    '''
    Raise error in capture_and_send (internal)
    '''
    logs.error(message_format.format(camera))
    notifications.publish(
        message=message_format.format(camera),
        tags='x,video_camera',
        topic=topic,
    )

def _capture_and_send_thread(
        camera: str,
        message: str = None,
        title: str = None,
        priority: notifications.Priority = None,
        priority_first: notifications.Priority = None,
        tags: str = 'video_camera',
        topic: str = None,
        low_res: bool = False,
        count = 1,
        delay = 1,
    ):
    '''
    Capture a photo from a camera and send it as notification (internal, see capture_and_send())
    '''
    camera = camera.lower()
    host = _get_host(camera)

    credentials = ''
    if _camera_rtsp_accesskey[camera]:
        credentials = '{}@'.format(_camera_rtsp_accesskey[camera])

    if not message:
        message = 'Photo from camera {}'.format(camera)

    if priority is None:
        priority = notifications.Priority.NORMAL
    if priority_first is None:
        priority_first = priority

    stream = _camera_stream[camera]
    if low_res and _camera_stream_low_def[camera]:
        stream = _camera_stream_low_def[camera]

    if count < 1:
        count = 1
    count_total = count
    first_photo = True

    if delay < 1:
        delay = 1

    while count >= 1:
        with _camera_locks[camera]:
            if _camera_thread_token[camera] == _TOKEN_INACTIVE:
                break
            if is_reachable(camera):
                cap = cv2.VideoCapture('rtsp://{}{}/{}'.format(credentials, host, stream))
                try:
                    if not cap.isOpened():
                        return _capture_error(camera, topic, 'Failed to access RTSP stream for camera: {}')
                    ret, frame = cap.read()
                    if not ret:
                        return _capture_error(camera, topic, 'Failed to capture image from RTSP stream for camera: {}')
                    filename = '{}_{}.jpg'.format(camera, datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))
                    # ret = cv2.imwrite(filename, frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
                    ret, jpg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80]) # jpeg quality = 80%
                    if not ret:
                        return _capture_error(camera, topic, 'Failed to encode RTSP image from camera: {}')
                    notification_message = message
                    if count_total > 1:
                        notification_message = '{} ({}/{})'.format(message, count_total - count + 1, count_total)
                    notifications.publish(
                        title=title,
                        message=notification_message,
                        priority=priority_first if first_photo else priority,
                        tags=tags,
                        topic=topic,
                        attachment=bytes(jpg),
                        filename=filename
                    )
                finally:
                    cap.release()
                first_photo = False
                count -= 1
                if count >= 1:
                    time.sleep(delay)
            else:
                return _capture_error(camera, topic, 'Camera is not reachable: {}')

def capture_and_send(
        camera: str,
        message: str = None,
        title: str = None,
        priority: notifications.Priority = None,
        priority_first: notifications.Priority = None,
        tags: str = 'video_camera',
        topic: str = None,
        low_res: bool = False,
        count = 1,
        delay = 1,
        synchronous: bool = False,
    ):
    '''
    Capture a photo from a camera and send it as notification
    message: Message to attach to the capture
    title: Title for the message to attach to the capture
    priority: Notification priority. Default is lowest (silent).
    priority_first: Different priority for the first photo of a series (see count)
    tags: Notification tags, see notification.publish().
    topic: Notification topic, see notification.publish().
    low_res: Make a low resolution capture to save bandwidth.
    count: Amount of photos to take
    delay: Delay between each photo in seconds
    synchronous: Wait for capture(s) to finish before returning
    '''
    if synchronous:
        return _capture_and_send_thread(
            camera=camera,
            message=message,
            title=title,
            priority=priority,
            priority_first=priority_first,
            tags=tags,
            topic=topic,
            low_res=low_res,
            count=count,
            delay=delay,
        )
    else:
        _capture_thread = Thread(target=_capture_and_send_thread,
            kwargs={
                'camera': camera,
                'message': message,
                'title': title,
                'priority': priority,
                'priority_first': priority_first,
                'tags': tags,
                'topic': topic,
                'low_res': low_res,
                'count': count,
                'delay': delay,
            },
            name='Capture and send (camera={}, title={})'.format(camera, title))
        _capture_thread.start()
        while _capture_thread.is_alive() and not _camera_locks[camera].locked():
            time.sleep(0.05) # make sure the lock is acquired before returning

def _monitor_thread(camera: str, topic: str, thread_token: int):
    '''
    Monitor camera and regularly send captures as notification
    '''
    frequency = _camera_screenshot_frequency_minutes[camera]
    frequency_desc = '📷 Si un évènement se produit'
    if frequency > 0:
        if frequency % 60 == 0:
            if frequency == 60:
                frequency_desc = '📷 Toutes les heures'
            else:
                frequency_desc = '📷 Toutes les {} heures'.format(frequency / 60)
        else:
            if frequency == 1:
                frequency_desc = '📷 Toutes les minutes'
            else:
                frequency_desc = '📷 Toutes les {} minutes'.format(frequency)

    if _camera_power_socket[camera]:
        # Minimum delay for camera to initialize
        time.sleep(75)

    camera_lost = False
    if wait_for_camera(camera):
        capture_and_send(camera,
            title='Démarrage caméra : {}'.format(camera),
            message=frequency_desc,
            tags='arrow_forward,video_camera',
            topic=topic
        )
    else:
        notifications.publish(
            message="La caméra n'a pas démarré : {}".format(camera),
            tags='x,video_camera',
            topic=topic,
            priority=notifications.Priority.HIGH
        )
        camera_lost = True

    take_screenshots = frequency > 0
    next_screenshot_time = time.time() + (frequency * 60)

    while True:
        if thread_token != _camera_thread_token[camera]:
            break

        if is_reachable(camera):
            if camera_lost:
                camera_lost = False
                capture_and_send(camera,
                    message="La caméra est revenue : {}".format(camera),
                    tags='heavy_check_mark,video_camera',
                    topic=topic,
                )
            else:
                if take_screenshots and time.time() >= next_screenshot_time:
                    capture_and_send(camera,
                        message="Photo de la caméra : {}".format(camera),
                        tags='video_camera',
                        priority=notifications.Priority.LOWEST,
                        low_res=True,
                        topic=topic,
                    )
                    next_screenshot_time = time.time() + (frequency * 60)
        elif not camera_lost:
            camera_lost = True
            notifications.publish(
                message='La caméra ne répond plus : {}'.format(camera),
                tags='x,video_camera',
                topic=topic,
                priority=notifications.Priority.HIGH
            )

        time.sleep(60) # 1 minute

def start_monitoring(camera: str = None, topic: str = None):
    '''
    Start monitoring cameras and sending photos automatically
    Automatically turn ON cameras having an associated power socket.
    camera: Name of camera to monitor (default: all cameras)
    '''
    cameras = _param_to_camera_list(camera)
    for camera in cameras:
        logs.info('Starting monitoring for camera: {}'.format(camera))
        if _camera_power_socket[camera]:
            _switch_camera_socket(camera=camera, on=True)
        with _camera_locks[camera]:
            thread_token = round(time.time() * 1000)
            if _camera_thread_token.get(camera, _TOKEN_INACTIVE) == thread_token:
                thread_token -= 1;
            _camera_thread_token[camera] = thread_token
            t = Thread(target=_monitor_thread, args=[camera, topic, thread_token], name='Camera monitor : {}'.format(camera))
            t.start()

def _stop_monitoring_thread(camera: str = None, topic: str = None):
    '''
    Stop monitoring cameras and sending photos automatically (internal thread)
    Automatically turn OFF cameras having an associated power socket.
    camera: Name of camera to monitor (default: all cameras)
    topic: Channel for posting notifications (see notification.publish())
    '''
    cameras = _param_to_camera_list(camera)
    for camera in cameras:
        if _camera_thread_token[camera] == _TOKEN_INACTIVE:
            logs.debug('Monitoring already stopped for camera: {}'.format(camera))
        else:
            logs.info('Stopping monitoring for camera: {}'.format(camera))
            with _camera_locks[camera]:
                _camera_thread_token[camera] = _TOKEN_INACTIVE
            notifications.publish(
                message="Arrêt caméra : {}".format(camera),
                tags='stop_button,video_camera',
                topic=topic,
            )
            if _camera_power_socket[camera]:
                _switch_camera_socket(camera=camera, on=False)

def stop_monitoring(camera: str = None, topic: str = None, synchronous: bool = False):
    '''
    Stop monitoring cameras and sending photos automatically
    Automatically turn OFF cameras having an associated power socket.
    camera: Name of camera to monitor (default: all cameras)
    topic: Channel for posting notifications (see notification.publish())
    synchronous: Wait for monitoring to stop before returning
    '''
    if synchronous:
        _stop_monitoring_thread(camera=camera, topic=topic)
    else:
        t = Thread(target=_stop_monitoring_thread, args=[camera, topic], name='Stop camera monitoring (camera={}, topic={})'.format(camera, topic))
        t.start()
