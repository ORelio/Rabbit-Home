#!/usr/bin/env python3

# ======================================
# webui - Serves static files for Web UI
# By ORelio (c) 2025 - CDDL 1.0
# ======================================

from configparser import ConfigParser
from flask import Blueprint, send_from_directory

config = ConfigParser()
config.read('config/webui.ini')
enabled = config.getboolean('WebUI', 'enabled')
path = config.get('WebUI', 'path')

web_ui = Blueprint('web_ui', __name__)

@web_ui.route(path)
@web_ui.route(path + '<path:file_path>')
def serve_ui(file_path = 'index.html'):
    if enabled:
        return send_from_directory('webui', file_path)
    return 'Forbidden', 403
