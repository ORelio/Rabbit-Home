#!/usr/bin/env python3

# ==============================================================
# notifications - send phone notifications using https://ntfy.sh
# By ORelio (c) 2024 - CDDL 1.0
# ==============================================================

import requests
import base64

from configparser import ConfigParser
from threading import Thread

import logging
import rabbits

from logs import logs

config = ConfigParser()
config.read('config/notifications.ini')
enabled = config.getboolean('Notifications', 'enabled', fallback=False)
service_url = config.get('Notifications', 'service')
publish_topic = config.get('Notifications', 'topic')
access_token = config.get('Notifications', 'token', fallback=None)
rabbits_as_topic = config.getboolean('Notifications', 'rabbits_as_topic', fallback=False)
if not service_url.endswith('/'):
    service_url = service_url + '/'

def _publish(message, title=None, priority=None, tags=None, rabbit=None, auto_trim=True):
    if not enabled:
        raise AssertionError('Calling _publish() but "enabled" is set to "False" in config')

    topic = publish_topic
    if rabbit and rabbits_as_topic:
        topic = rabbits.get_name(rabbit).lower()

    headers = {
        'Content-Type': 'text/plain; charset=utf-8'
    }

    if access_token and len(access_token) > 0:
        headers['Authorization'] = 'Bearer {}'.format(access_token)
    if title:
        headers['Title'] = '=?UTF-8?B?{}?='.format(base64.b64encode(title.encode(encoding='utf-8')).decode('ascii'));
    if priority:
        headers['Priority'] = priority
    if tags:
        headers['Tags'] = tags

    message = message.encode(encoding='utf-8')
    if auto_trim and len(message) > 4095:
        message = message[:4092] + '...'.encode('utf-8')

    resp = requests.post(service_url + topic, data=message, headers=headers)
    resp.raise_for_status()

def publish(message, title=None, priority=None, tags=None, rabbit=None, synchronous=False, auto_trim=True):
    '''
    Publish a phone notification using ntfy
    message: Notification message
    title: (optional) Notification title
    priority: (optional) Priority as per https://docs.ntfy.sh/publish/#message-priority
    tags: (optional) Comma-separated emoji names as per https://docs.ntfy.sh/emojis/
    rabit: (optional) Rabbit related to the notification
    synchronous: (optional) Wait for server to accept message before returning
    auto_trim: (optional) Auto trim long messages to fit in size limit. Beyond the limit, server will auto-convert long messages to attachments.
    '''
    logs.info('{}: {} (title: {}, priority: {}, tags: {}, rabbit: {})'.format('Publishing' if enabled else 'Would publish if enabled', message, title, priority, tags, rabbit))
    if enabled:
        if synchronous:
            _publish(message, title=title, priority=priority, tags=tags, rabbit=rabbit, auto_trim=auto_trim)
        else:
            _request_thread = Thread(target=_publish, args=[message], kwargs={'title': title, 'priority': priority, 'tags':tags, 'rabbit': rabbit, 'auto_trim': auto_trim }, name='Ntfy request')
            _request_thread.start()
