#!/usr/bin/env python3

# ========================================================
# rabbits - module for listing rabbits through config file
# allows conveniently resolving rabbit name to IP address
# By ORelio (c) 2023 - CDDL 1.0
# ========================================================

from configparser import ConfigParser

config = ConfigParser()
config.read('config/rabbits.ini')

_rabbits_name_to_ip = {}
_rabbits_ip_to_name = {}

for name in config.options('Rabbits'):
    ip = config.get('Rabbits', name)
    if name in _rabbits_name_to_ip:
        raise ValueError('Duplicate rabbit name: ' + name)
    if ip in _rabbits_ip_to_name:
        raise ValueError('Duplicate rabbit IP: ' + ip)
    _rabbits_name_to_ip[name] = ip
    _rabbits_ip_to_name[ip] = name

def get_all():
    '''
    Get a list of all rabbits
    '''
    return list(_rabbits_name_to_ip.keys())

def get_ip(rabbit):
    '''
    Resolve IP address of a rabbit
    '''
    if rabbit is None:
        return None
    if rabbit.lower() in _rabbits_name_to_ip:
        return _rabbits_name_to_ip[rabbit] # name => ip
    if rabbit in _rabbits_ip_to_name:
        return rabbit # already an ip address
    raise KeyError('Unknown Rabbit or IP: ' + rabbit)

def get_name(rabbit):
    '''
    Get name of a rabbit from its IP address
    '''
    if rabbit is None:
        return None
    if rabbit in _rabbits_ip_to_name:
        return _rabbits_ip_to_name[rabbit] # ip => name
    if rabbit.lower() in _rabbits_name_to_ip:
        return rabbit.lower() # already a rabbit name
    raise KeyError('Unknown Rabbit or IP: ' + rabbit)

def is_rabbit(rabbit):
    '''
    Check if the provided string matches a known rabbit by its name or IP
    '''
    return rabbit is not None and rabbit.lower() in _rabbits_name_to_ip or rabbit in _rabbits_ip_to_name
