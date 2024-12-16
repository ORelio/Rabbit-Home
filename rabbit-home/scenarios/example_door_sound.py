#!/usr/bin/env python3

# Example scenario: Play sound when opening door

from scenarios import Event, subscribe, unsubscribe
from windows import WindowState

import soundplayer

from logs import logs

def init():
    subscribe(Event.WINDOW, run)

def run(event: Event, rabbit: str = None, args: dict = {}):
    if 'window' in args and 'state' in args:
        if args['state'] == WindowState.OPEN:
            sound = 'door_open.mp3'
        else:
            sound = 'door_close.mp3'
        logs.info('Window event {}, {}, playing: {}'.format(args['window'], args['state'].name, sound))
        soundplayer.play(sound, rabbit=rabbit)
