#!/usr/bin/env python3

# Example scenario: Play sound when opening door

from scenarios import Event, subscribe, unsubscribe
from openings import OpenState

import soundplayer

from logs import logs

def init():
    subscribe(Event.OPEN_CLOSE, run)

def run(event: Event, rabbit: str = None, args: dict = {}):
    if 'opening' in args and 'state' in args:
        if args['state'] == OpenState.OPEN:
            sound = 'door_open.mp3'
        else:
            sound = 'door_close.mp3'
        logs.info('Open/Close event {}, {}, playing: {}'.format(args['opening'], args['state'].name, sound))
        soundplayer.play(sound, rabbit=rabbit)
