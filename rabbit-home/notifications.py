#!/usr/bin/env python3

# ==============================================================
# notifications - send phone notifications using https://ntfy.sh
# By ORelio (c) 2024-2025 - CDDL 1.0
# ==============================================================

import requests
import base64

from configparser import ConfigParser
from threading import Thread
from strenum import StrEnum

import logging
import rabbits

from logs import logs

class Priority(StrEnum):
    HIGHEST = 'max'
    HIGH = 'high'
    NORMAL = 'default'
    LOW = 'low'
    LOWEST = 'min'

config = ConfigParser()
config.read('config/notifications.ini')
enabled = config.getboolean('Notifications', 'enabled', fallback=False)
service_url = config.get('Notifications', 'service')
default_publish_topic = config.get('Notifications', 'default_topic')
access_token = config.get('Notifications', 'token', fallback=None)
rabbits_as_topic = config.getboolean('Notifications', 'rabbits_as_topic', fallback=False)
if not service_url.endswith('/'):
    service_url = service_url + '/'

def _encode_header_b64(text: str) -> str:
    return '=?UTF-8?B?{}?='.format(base64.b64encode(text.encode(encoding='utf-8')).decode('ascii'))

def _publish(message, title=None, priority=None, tags=None, topic=None, rabbit=None, auto_trim=True, attachment=None, filename=None):
    if not enabled:
        raise AssertionError('Calling _publish() but "enabled" is set to "False" in config')

    if not topic:
        topic = default_publish_topic
        if rabbit and rabbits_as_topic:
            topic = rabbits.get_name(rabbit).lower()

    max_length = 4095 if not attachment else 2047
    if auto_trim and len(message) > max_length:
        message = message[:max_length - 3] + '...'

    headers = {}

    if access_token and len(access_token) > 0:
        headers['Authorization'] = 'Bearer {}'.format(access_token)

    if title:
        headers['Title'] = _encode_header_b64(title)

    if priority:
        headers['Priority'] = '{}'.format(priority)

    if tags:
        headers['Tags'] = tags

    if attachment:
        headers['Message'] = _encode_header_b64(message)
        if filename:
            headers['Filename'] = _encode_header_b64(filename)
        request_data = attachment
    else:
        headers['Content-Type'] = 'text/plain; charset=utf-8'
        request_data = message.encode('utf-8')

    resp = requests.post(service_url + topic, data=request_data, headers=headers)
    resp.raise_for_status()

def publish(message, title=None, priority=None, tags=None, topic=None, rabbit=None, synchronous=False, auto_trim=True, attachment=None, filename=None):
    '''
    Publish a phone notification using ntfy
    message: Notification message, up to 4095 characters, or 2047 when an attachment is set (see auto_trim parameter).
    title: (optional) Notification title
    priority: (optional) See Priority enum and https://docs.ntfy.sh/publish/#message-priority
    tags: (optional) Comma-separated emoji names as per https://docs.ntfy.sh/emojis/
    topic: (optional) Specify in which channel the notification will be posted
    rabit: (optional) Rabbit related to the notification (used as topic if not specified otherwise)
    synchronous: (optional) Wait for server to accept message before returning
    auto_trim: (optional) Auto trim long messages to fit in size limit. Beyond the limit, server may auto-convert long messages to attachments or reject the request.
    attachment: (optional) Attach a file to the notification. Can be bytes or file-like object.
    filename: (optional) Attachment file name, e.g. 'image.png'. If missing, file name is assigned by the server.
    '''
    logs.info('{}: {} (title: {}, priority: {}, tags: {}, rabbit: {})'.format('Publishing' if enabled else 'Would publish if enabled', message, title, priority, tags, rabbit))
    if enabled:
        if synchronous:
            _publish(message,
                title=title,
                priority=priority,
                tags=tags,
                topic=topic,
                rabbit=rabbit,
                auto_trim=auto_trim,
                attachment=attachment,
                filename=filename)
        else:
            _request_thread = Thread(target=_publish, args=[message], kwargs={
                    'title': title,
                    'priority': priority,
                    'tags':tags,
                    'topic': topic,
                    'rabbit': rabbit,
                    'auto_trim': auto_trim,
                    'attachment': attachment,
                    'filename': filename
                }, name='Ntfy request')
            _request_thread.start()
