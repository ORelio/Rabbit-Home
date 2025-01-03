#!/usr/bin/env python3

# =====================================================
# weather - Retrieve weather forecast from Meteo France
# https://github.com/hacf-fr/meteofrance-api
# By ORelio (c) 2024 - CDDL 1.0
# =====================================================

from meteofrance_api.client import MeteoFranceClient, Place
from daycycle import _latitude, _longitude
from datetime import datetime
from threading import Lock

from logs import logs

_lock = Lock()
_last_refresh_hour = None
_last_forecast_cache = None

# Example of API responses

# >>> client.get_forecast_for_place(Place({'lat': xx.xxxxxx, 'lon': xx.xxxxxx})).today_forecast
# {'dt': 17xxxxxxxx, 'T': {'min': 17.9, 'max': 34.2, 'sea': None}, 'humidity': {'min': 35, 'max': 85}, 'precipitation': {'24h': 0}, 'uv': 7, 'weather12H': {'icon': 'p2j', 'desc': 'Eclaircies'}, 'sun': {'rise': 17xxxxxxxx, 'set': 17xxxxxxxx}}

# >>> client.get_forecast_for_place(Place({'lat': xx.xxxxxx, 'lon': xx.xxxxxx})).nearest_forecast
# {'dt': 17xxxxxxxx, 'T': {'value': 30.6, 'windchill': 38.2}, 'humidity': 55, 'sea_level': 1013.5, 'wind': {'speed': 3, 'gust': 0, 'direction': 235, 'icon': 'SO'}, 'rain': {'1h': 0}, 'snow': {'1h': 0}, 'iso0': 4050, 'rain snow limit': 'Non pertinent', 'clouds': 40, 'weather': {'icon': 'p2j', 'desc': 'Eclaircies'}}

def _refresh_forecast():
    '''
    Refresh forecast cache, avoids hammering the Meteo France API
    Cache expires every hour so API can be refreshed once per hour
    '''
    global _last_refresh_hour
    global _last_forecast_cache
    _lock.acquire()
    current_hour = datetime.now().strftime('%Y-%m-%d-%H')
    if current_hour != _last_refresh_hour:
        _last_refresh_hour = current_hour
        try:
            client = MeteoFranceClient()
            _last_forecast_cache = client.get_forecast_for_place(Place({'lat': _latitude, 'lon': _longitude}))
            logs.info('Refreshed forecast for lat={}, long={}: min={}, current={}, max={}'.format(
                _latitude, _longitude,
                _last_forecast_cache.today_forecast['T']['min'],
                _last_forecast_cache.nearest_forecast['T']['value'],
                _last_forecast_cache.today_forecast['T']['max']))
        except:
            logs.error('Failed to refresh forecast, API seems unreachable.')
            _last_forecast_cache = None
    _lock.release()

def get_current_temperature():
    '''
    Get current temperature, or None if unavailable
    '''
    _refresh_forecast()
    if _last_forecast_cache is None:
        return None
    return _last_forecast_cache.nearest_forecast['T']['value']

def get_today_minimum_temperature():
    '''
    Get minimum temperature for today, or None if unavailable
    '''
    _refresh_forecast()
    if _last_forecast_cache is None:
        return None
    return _last_forecast_cache.today_forecast['T']['min']

def get_today_maximum_temperature():
    '''
    Get minimum temperature for today, or None if unavailable
    '''
    _refresh_forecast()
    if _last_forecast_cache is None:
        return None
    return _last_forecast_cache.today_forecast['T']['max']

_refresh_forecast()
