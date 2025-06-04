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
import rabbits
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
_camera_rabbit = {}
_camera_screenshot_frequency_minutes = {}
_camera_screenshot_channel = {}
_camera_power_socket = {}

_rabbit_to_cameras = {}

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
    camera_screenshot_channel = config.get(camera_name_raw, 'ScreenshotsChannel', fallback=None)
    camera_power_socket = config.get(camera_name_raw, 'PowerSocket', fallback=None)
    rabbit = rabbits.get_name(config.get(camera_name_raw, 'Rabbit', fallback=None))
    if rabbit:
        if not rabbit in _rabbit_to_cameras:
            _rabbit_to_cameras[rabbit] = []
        _rabbit_to_cameras[rabbit].append(camera_name)
    _cameras.append(camera_name)
    _camera_locks[camera_name] = Lock()
    _camera_should_monitor[camera_name] = False
    _camera_thread_token[camera_name] = _TOKEN_INACTIVE
    _camera_ip[camera_name] = camera_ip
    _camera_port[camera_name] = camera_port
    _camera_stream[camera_name] = camera_stream
    _camera_stream_low_def[camera_name] = camera_stream_low_def
    _camera_rtsp_accesskey[camera_name] = camera_rtsp_accesskey
    _camera_rabbit[camera_name] = rabbit
    _camera_screenshot_frequency_minutes[camera_name] = camera_screenshot_frequency_minutes
    _camera_screenshot_channel[camera_name] = camera_screenshot_channel
    _camera_power_socket[camera_name] = camera_power_socket
    logs.debug(('Loaded camera "{}" (IP={}, Port={}, Stream={}, StreamLowDef={}, Account={}, Rabbit={}, '
        + 'ScreenshotFrequency={}min, ScreenshotChannel={}, PowerSocket={})').format(
            camera_name,
            camera_ip,
            camera_port,
            camera_stream,
            camera_stream_low_def,
            rtsp_login,
            rabbit,
            camera_screenshot_frequency_minutes,
            camera_screenshot_channel,
            camera_power_socket
    ))
logs.debug('Loaded {} camera definitions'.format(len(_cameras)))

def get_for_rabbit(rabbit: str) -> list:
    '''
    Get all cameras associated with a rabbit
    '''
    rabbit = rabbits.get_name(rabbit)
    if not rabbit in _rabbit_to_cameras:
        return []
    return _rabbit_to_cameras[rabbit]

def _get_host(camera: str) -> str:
    '''
    Get ip:port from camera name
    '''
    camera = camera.lower()
    if not camera in _cameras:
        raise ValueError('Unknown camera: {}'.format(camera))
    return '{}:{}'.format(_camera_ip[camera], _camera_port[camera])

def _params_to_camera_list(camera: str = None, rabbit: str = None) -> list:
    '''
    Convert param to list of cameras (internal)
    '''
    if camera and rabbit:
        raise ValueError('Specify either "camera" or "rabbit" but not both')
    cameras = _cameras
    if camera:
        cameras = [camera]
    if rabbit:
        cameras = get_for_rabbit(rabbit)
    return cameras

def _switch_camera_socket(on: bool, camera: str = None, rabbit: str = None):
    '''
    Switch cameras ON or OFF
    on: Desired ON/OFF state, True means ON, False means OFF
    camera: Name of camera to switch (default: all cameras)
    rabbit: Switch cameras for the specified rabbit (mutually exclusive with 'camera')
    '''
    cameras = _params_to_camera_list(camera=camera, rabbit=rabbit)
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
        requests.get('http://{}/'.format(host), timeout=timeout_seconds)
    except requests.exceptions.ConnectionError as e:
        if len(e.args) > 0 \
          and len(e.args[0].args) > 1 \
          and str(e.args[0].args[1]).strip() == 'RTSP/1.0 400 Bad Request':
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

def _capture_error(camera, message_format):
    '''
    Raise error in capture_and_send (internal)
    '''
    logs.error(message_format.format(camera))
    notifications.publish(
        message=message_format.format(camera),
        tags='x,video_camera',
        topic=_camera_screenshot_channel[camera],
        rabbit=_camera_rabbit[camera]
    )

def capture_and_send(
        camera: str,
        message: str = None,
        title: str = None,
        priority: notifications.Priority = None,
        priority_first: notifications.Priority = None,
        tags: str = 'video_camera',
        low_res: bool = False,
        count = 1,
        delay = 1,
    ):
    '''
    Capture a photo from a camera and send it as notification
    message: Message to attach to the capture
    title: Title for the message to attach to the capture
    priority: Notification priority. Default is lowest (silent).
    priority_first: Different priority for the first photo of a series (see count)
    tags: Notification tags, see notification.publish().
    low_res: Make a low resolution capture to save bandwidth.
    count: Amount of photos to take
    delay: Delay between each photo in seconds
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

    with _camera_locks[camera]:
        while count >= 1:
            if is_reachable(camera):
                cap = cv2.VideoCapture('rtsp://{}{}/{}'.format(credentials, host, stream))
                try:
                    if not cap.isOpened():
                        return _capture_error(camera, 'Failed to access RTSP stream for camera: {}')
                    ret, frame = cap.read()
                    if not ret:
                        return _capture_error(camera, 'Failed to capture image from RTSP stream for camera: {}')
                    filename = '{}_{}.jpg'.format(camera, datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))
                    # ret = cv2.imwrite(filename, frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
                    ret, jpg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80]) # jpeg quality = 80%
                    if not ret:
                        return _capture_error(camera, 'Failed to encode RTSP image from camera: {}')
                    notification_message = message
                    if count_total > 1:
                        notification_message = '{} ({}/{})'.format(message, count_total - count + 1, count_total)
                    notifications.publish(
                        title=title,
                        message=notification_message,
                        priority=priority_first if first_photo else priority,
                        tags=tags,
                        topic=_camera_screenshot_channel[camera],
                        rabbit=_camera_rabbit[camera],
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
                return _capture_error(camera, 'Camera is not reachable: {}')

def _monitor_thread(camera: str, thread_token: int):
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
            tags='arrow_forward,video_camera'
        )
    else:
        notifications.publish(
            message="La caméra n'a pas démarré : {}".format(camera),
            tags='x,video_camera',
            topic=_camera_screenshot_channel[camera],
            rabbit=_camera_rabbit[camera],
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
                    tags='heavy_check_mark,video_camera'
                )
            else:
                if take_screenshots and time.time() >= next_screenshot_time:
                    capture_and_send(camera,
                        message="Photo de la caméra : {}".format(camera),
                        tags='video_camera',
                        priority=notifications.Priority.LOWEST,
                        low_res=True
                    )
                    next_screenshot_time = time.time() + (frequency * 60)
        elif not camera_lost:
            camera_lost = True
            notifications.publish(
                message='La caméra ne répond plus : {}'.format(camera),
                tags='x,video_camera',
                topic=_camera_screenshot_channel[camera],
                rabbit=_camera_rabbit[camera],
                priority=notifications.Priority.HIGH
            )

        time.sleep(60) # 1 minute

def start_monitoring(camera: str = None, rabbit: str = None):
    '''
    Start monitoring cameras and sending photos automatically
    Automatically turn ON cameras having an associated power socket.
    camera: Name of camera to monitor (default: all cameras)
    rabbit: Monitor cameras for the specified rabbit (mutually exclusive with 'camera')
    '''
    cameras = _params_to_camera_list(camera=camera, rabbit=rabbit)
    for camera in cameras:
        logs.info('Starting monitoring for camera: {}'.format(camera))
        if _camera_power_socket[camera]:
            _switch_camera_socket(camera=camera, on=True)
        with _camera_locks[camera]:
            thread_token = round(time.time() * 1000)
            if _camera_thread_token.get(camera, _TOKEN_INACTIVE) == thread_token:
                thread_token -= 1;
            _camera_thread_token[camera] = thread_token
            t = Thread(target=_monitor_thread, args=[camera, thread_token], name='Camera monitor : {}'.format(camera))
            t.start()

def _stop_monitoring_thread(camera: str = None, rabbit: str = None):
    '''
    Stop monitoring cameras and sending photos automatically (internal thread)
    Automatically turn OFF cameras having an associated power socket.
    camera: Name of camera to monitor (default: all cameras)
    rabbit: Monitor cameras for the specified rabbit (mutually exclusive with 'camera')
    '''
    cameras = _params_to_camera_list(camera=camera, rabbit=rabbit)
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
                topic=_camera_screenshot_channel[camera],
                rabbit=_camera_rabbit[camera]
            )
            if _camera_power_socket[camera]:
                _switch_camera_socket(camera=camera, on=False)

def stop_monitoring(camera: str = None, rabbit: str = None, synchronous: bool = False):
    '''
    Stop monitoring cameras and sending photos automatically
    Automatically turn OFF cameras having an associated power socket.
    camera: Name of camera to monitor (default: all cameras)
    rabbit: Monitor cameras for the specified rabbit (mutually exclusive with 'camera')
    synchronous: Wait for monitoring to stop before returning
    '''
    if synchronous:
        _stop_monitoring_thread(camera=camera, rabbit=rabbit)
    else:
        t = Thread(target=_stop_monitoring_thread, args=[camera, rabbit], name='Stop camera monitoring (camera={}, rabbit={})'.format(camera, rabbit))
        t.start()
