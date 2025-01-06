#!/usr/bin/env python3

# ==================================================================
# Rabbit Home
#
# Service for managing nabaztags at home for the purpose of extendig
# functionality without touching the existing pynab codebase,
# as well as making automation scenarios
#
# By ORelio (c) 2023-2024 - CDDL 1.0
# ==================================================================

import os

# Make sure working directory is script directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Static module initialization
import rabbits
import rfid
import infrared
import pcremote
import switches
import openings
import soundplayer
import httpserver

httpserver.run()
