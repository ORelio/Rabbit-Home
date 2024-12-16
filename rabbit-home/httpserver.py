#!/usr/bin/env python3

# ========================================
# httpserver - HTTP server for module APIs
# By ORelio (c) 2023-2024 - CDDL 1.0
# ========================================

from configparser import ConfigParser
from flask import Flask

import soundplayer

from logs import logs
from nabstate import nabstate_api
from scenarios import scenarios_api
from pcstate import pcstate_api
from soundplayer import soundplayer_api

config = ConfigParser()
config.read('config/httpserver.ini')
bind_ip = config.get('Server', 'ip')
bind_port = config.getint('Server', 'port')
url = config.get('Server', 'url', fallback=None)

app = Flask(__name__)
app.logger = logs
app.register_blueprint(nabstate_api)
app.register_blueprint(scenarios_api)
app.register_blueprint(pcstate_api)
app.register_blueprint(soundplayer_api)

soundplayer.set_base_url(url)

def run():
    app.run(host=bind_ip, port=bind_port)
