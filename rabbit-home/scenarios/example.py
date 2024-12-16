from scenarios import Event, subscribe, unsubscribe
from logs import logs
import rabbits
import nabstate

# Persistent variable between runs
event_count = 0

def init():
    logs.info('init()')
    logs.info('Registering sleep callback')
    subscribe(Event.SLEEP, run)

def run(event: Event, rabbit: str = None, args: dict = {}):
    global event_count
    event_count = event_count + 1
    nabaztag_name = rabbits.get_name(rabbit)
    logs.info('run()')
    logs.info('event_count: ' + str(event_count))
    logs.info('event: ' + str(event))
    logs.info('rabbit: ' + nabaztag_name)
    logs.info('args: ' + str(args))
    if rabbit != None and event != Event.SLEEP and nabstate.get_state(rabbit) != nabstate.STATE_ASLEEP:
        logs.info('Putting rabbit to sleep: ' + nabaztag_name)
        nabstate.set_sleeping(nabaztag_name, sleeping=True, play_sound=False)
        logs.info('Scheduling wakeup callback')
        subscribe(Event.WAKEUP, sleep_callback)
    else:
        logs.info('Not taking actions for now')

def sleep_callback(event: Event, rabbit: str = None, args: dict = {}):
    unsubscribe(event, sleep_callback) # This event listener only happens once, then get unregistered
    logs.info('The rabbit I put asleep is now awake!')
    # Do something specific after I put rabbit asleep (e.g. end of night time scenario, or do not disturb scenario)
