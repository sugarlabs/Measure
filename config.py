#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2009,10 Walter Bender
#    Copyright (C) 2009, Benjamin Berg, Sebastian Berg
#    	
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

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

# Toolbars for 0.84- Sugar
TOOLBARS = ['project','sound','sensor']

# Maximum no. of screenshots Measure will save while recording in Sound context
SOUND_MAX_WAVE_LOGS = 10

# Duty cycle of display value update
DISPLAY_DUTY_CYCLE = 100

# Hardware configurations
XO1 = 'xo1'
XO15 = 'xo1.5'
UNKNOWN = 'unknown'
