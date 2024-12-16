from scenarios import Event, subscribe, unsubscribe

import nabd

# =======================================================
# Example scenario - Rotate ears for the specified rabbit
# By ORelio (c) 2023-2024 - CDDL 1.0
# =======================================================

def run(event: Event, rabbit: str = None, args: dict = {}):
    nabd.publish(rabbit, [
        {"type":"ears", "left": 9, "right": 9},
        {"type":"ears", "left": 0, "right": 0}
    ])