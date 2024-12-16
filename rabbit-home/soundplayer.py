#!/usr/bin/env python3

# ============================================================================
# soundplayer - send audio files to a rabbit using nabd (Nabaztag/tag:tag:tag)
# By ORelio (c) 2024 - CDDL 1.0
# ============================================================================

from flask import Blueprint, send_from_directory
from typing import Union

import rabbits
import nabstate
import nabd

from logs import logs

_sound_file_api_url = None

def set_base_url(url):
    '''
    Set base URL for audio files, e.g. http://my_server/static
    See config/httpserver.ini
    '''
    global _sound_file_api_url
    _sound_file_api_url = url.strip('/') + '/api/v1/soundplayer/'

'''
Sound file API for serving sound files to rabbits
'''
soundplayer_api = Blueprint('soundplayer_api', __name__)

@soundplayer_api.route('/api/v1/soundplayer/<file_name>')
def serve_sound_file(file_name):
    '''
    API for serving sound files to rabbits
    '''
    return send_from_directory('sounds', file_name)

def play(audio_list: Union[str, list[str]], signature: str = None, rabbit: str = None, queue_if_sleeping: bool = False):
    '''
    Play a sound file on a rabbit
    audio_list: relative path of static sound file(s), e.g. "mysound.mp3" for "mysound.mp3" inside "static" dir
    signature: audio file played before and after audio_list file(s)
    rabbit: name of target rabbit. If missing, send audio message to all rabbits.
    queue_if_sleeping: If rabbit is sleeping, send anyway for playing on wakeup.
    '''
    log_message = 'Playing: {}'.format(audio_list)

    if isinstance(audio_list, str):
        audio_list = [audio_list]

    if _sound_file_api_url is None:
        raise AssertionError('Base URL not set before calling play(). Call set_base_url(url) first or see config/httpserver.ini')

    audio_list = [_sound_file_api_url + audio_file for audio_file in audio_list]
    message = {'type':'message', 'body':[{'audio':audio_list}]}
    if signature:
        log_message += ' (signature: {})'.format(signature)
        message['signature'] = {'audio':signature}

    if rabbit is None:
        targets = rabbits.get_all()
    else:
        log_message += ' (rabbit: {})'.format(rabbit)
        targets = [rabbits.get_name(rabbit)]

    logs.info(log_message)

    for rabbit in targets:
        if queue_if_sleeping or not nabstate.is_sleeping(rabbit):
            nabd.publish(rabbit, message)
        else:
            logs.debug('Skipping sleeping rabbit: {}'.format(rabbit))
