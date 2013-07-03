# Written by Arjun Sarwal <arjun@laptop.org>
# Copyright (C) 2007, Arjun Sarwal
# Copyright (C) 2009-11 Walter Bender
# Copyright (C) 2009, Benjamin Berg, Sebastian Berg
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA


"""
Global configuration for Measure.
"""

import os
try:
    from sugar.activity import activity
    MEASURE_ROOT = activity.get_bundle_path()
    SUGAR = True
except ImportError:
    MEASURE_ROOT = os.environ['HOME']
    SUGAR = False

from gettext import gettext as _

ICONS_DIR = os.path.join(MEASURE_ROOT, 'icons')

# Multiplied with width and height to set placement of text
TEXT_X_M = 0.65
TEXT_Y_M = 0.70

# Maximum number of graphs that can be simultaneously be displayed
MAX_GRAPHS = 4

# Device settings at start of Activity
RATE = 48000
MIC_BOOST = True
DC_MODE_ENABLE = False
CAPTURE_GAIN = 50
BIAS = True

# Interval, in ms, after which audio buffer will be sent to drawing class
AUDIO_BUFFER_TIMEOUT = 30

# When Activity quits
QUIT_MIC_BOOST = False
QUIT_DC_MODE_ENABLE = False
QUIT_CAPTURE_GAIN = 100
QUIT_BIAS = True

# Maximum no. of data samples Measure will save
MAX_LOG_ENTRIES = 1000

# Duty cycle of display value update
DISPLAY_DUTY_CYCLE = 100

# Hardware configurations
XO1 = 'xo1'
XO15 = 'xo1.5'
XO175 = 'xo1.75'
XO30 = 'xo3.0'
XO4 = 'xo4'
UNKNOWN = 'unknown'

# Bounds of side slider
LOWER = 0.0
UPPER = 4.0

# TRANS: Please use short versions of instrument names if possible
INSTRUMENT_DICT = {
    _('None'): [],
    _('Guitar'): [82.4069, 110, 146.832, 195.998, 246.942, 329.628],
    _('Violin'): [195.998, 293.665, 440, 659.255],
    _('Viola'): [130.813, 195.998, 293.665, 440],
    _('Cello'): [65.4064, 97.9989, 146.832, 220],
    _('Bass'): [41.2034, 55, 73.4162, 97.9989],
    #TRANS: a small Andean stringed instrument of the lute family
    _('Charango'): [329.63, 392, 440, 523.25, 659.26],
    #TRANS: a small string instrument (also called machimbo)
    _('Cavaquinho'): [293.665, 391.995, 493.883, 587.330],
    _('Ukulele'): [261.626, 329.628, 391.995, 440],
    _('Sitar'): [174.614, 130.813, 195.998, 65.4064, 391.995,
                            261.626, 523.251],
    _('Mandolin'): [195.998, 293.665, 440, 659.255],
    _('Recorder'): [391.995]
    }
