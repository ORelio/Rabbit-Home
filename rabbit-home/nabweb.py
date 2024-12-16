#!/usr/bin/env python3

# ==========================================================================================
# nabd - remotely update nabaztag configuration and launch actions through its web interface
# The web interface has no documented API but offers several settings enpoints
# By ORelio (c) 2023-2024 - CDDL 1.0
# ==========================================================================================

import requests
import rabbits

from logs import logs

'''
Nabclockd API. For use with change_settings.
The following settings can be passed to this API:
    "chime_hour": "true",
    "settings_per_day": "false",
    "wakeup_time": "07:00",
    "sleep_time": "22:00",
    "wakeup_time_monday": "07:00",
    "sleep_time_monday": "22:00",
    "wakeup_time_tuesday": "07:00",
    "sleep_time_tuesday": "22:00",
    "wakeup_time_wednesday": "07:00",
    "sleep_time_wednesday": "22:00",
    "wakeup_time_thursday": "07:00",
    "sleep_time_thursday": "22:00",
    "wakeup_time_friday": "07:00",
    "sleep_time_friday": "22:00",
    "wakeup_time_saturday": "07:00",
    "sleep_time_saturday": "22:00",
    "wakeup_time_sunday": "07:00",
    "sleep_time_sunday": "22:00",
    "timezone": "Europe/Paris",
    "play_wakeup_sleep_sounds": "true"
'''
API_NABCLOCKD='nabclockd/settings'

'''
Weather API. For use with launch_action.
One of the following arguments must be passed to this API:
    "type": "today"
    "type": "tomorrow"
'''
API_WEATHER='nabweatherd/settings'

'''
Air quality API. For use with launch_action.
Does not take any arguments
'''
API_AIRQUALITY='nabairqualityd/settings'

'''
Taichi API. For use with launch_action.
Does not take any arguments
'''
API_TAICHI='nabtaichid/settings'

def change_settings(rabbit: str, api_endpoint: str, request_data: dict, retries: int=2):
    '''
    Change Nabaztag settings through its WebUI
    rabbit: Name or IP of the Nabaztag
    api_endpoint: Endpoint to use. See constants defined above.
    request_data: Settings to change (as dict). See comments for each endpoint.
    retries: (optional) Amount of HTTP request retries. Nabaztag webserver may be slow on first request.
    '''
    _api_request(rabbit, 'POST', api_endpoint, request_data, retries)

def launch_action(rabbit: str, api_endpoint: str, request_data: dict={}, retries: int=2):
    '''
    Launch Nabaztag action through its WebUI
    rabbit: Name or IP of the Nabaztag
    api_endpoint: Endpoint to use. See constants defined above.
    request_data: Settings to change (as dict). See comments for each endpoint.
    retries: (optional) Amount of HTTP request retries. Nabaztag webserver may be slow on first request.
    '''
    _api_request(rabbit, 'PUT', api_endpoint, request_data, retries)

def launch_weather(rabbit: str, tomorrow: bool=False):
    '''
    Launch Weather action
    '''
    args = { 'type': 'today' }
    if tomorrow:
        args['type'] = 'tomorrow'
    launch_action(rabbit, API_WEATHER, args)

def launch_airquality(rabbit: str):
    '''
    Launch Air Quality action
    '''
    launch_action(rabbit, API_AIRQUALITY)

def launch_taichi(rabbit: str):
    '''
    Launch Taichi action
    '''
    launch_action(rabbit, API_TAICHI)

def _api_request(rabbit: str, request_type: str, api_endpoint: str, request_data: dict, retries: int=2):
    '''
    Make a Nabaztag WebUI API request
    rabbit: Name or IP of the Nabaztag
    request_type: Type of request (get, post, put)
    api_endpoint: Endpoint to use. See constants defined above.
    request_data: Settings to change (as dict). See comments for each endpoint.
    retries: (optional) Amount of HTTP request retries. Nabaztag webserver may be slow on first request.
    '''
    try:
        nabaztag_ip = rabbits.get_ip(rabbit)
        url = f"http://{nabaztag_ip}/{api_endpoint}"
        session = requests.Session()
        read_request = session.get(url)
        if request_type == 'POST':
            request_data['csrfmiddlewaretoken'] = read_request.cookies['csrftoken']
            session.post(url, data=request_data)
        elif request_type == 'PUT':
            request_headers = {'X-CSRFToken': read_request.cookies['csrftoken']}
            session.put(url, data=request_data, headers=request_headers)
        else:
            raise ValueError('Request type not implemented: ' + request_type)
    except requests.exceptions.ConnectionError:
        if retries <= 0:
            logs.debug(f"in _api_request({rabbit}, {request_type}, {api_endpoint}, {str(request_data)}, {retries}):")
            raise
        _api_request(rabbit, request_type, api_endpoint, request_data, retries - 1)
