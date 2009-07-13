import os
import os.path
import tempfile
from sugar.activity import activity

MEASURE_ROOT = activity.get_bundle_path()
ICONS_DIR = MEASURE_ROOT + '/icons'


#Waveform drawing area dimensions
WINDOW_W=1200.0
WINDOW_H=700.0


#In milliseconds, the delay interval after which the waveform draw function will be queued"
REFRESH_TIME = 30

#Multiplied with width and height to set placement of text
TEXT_X_M = 0.65
TEXT_Y_M = 0.70

#Maximum number of graphs that can be simultaneously be displayed
MAX_GRAPHS = 4

#Device settings at start of Activity
RATE = 48000
MIC_BOOST = True
DC_MODE_ENABLE = False
CAPTURE_GAIN = 50
BIAS = True

#Interval, in ms, after which audio buffer will be sent to drawing class
AUDIO_BUFFER_TIMEOUT = 30

#When Activity quits
QUIT_MIC_BOOST = False
QUIT_DC_MODE_ENABLE = False
QUIT_CAPTURE_GAIN = 100
QUIT_BIAS = True
QUIT_PCM = 70

#Which context is active on start
# 1 - sound
# 2 - sensors
CONTEXT = 1

#How many maximum screenshots Measure will save while recording in Sound context
SOUND_MAX_WAVE_LOGS = 10

#To track if one context is logging, other wouldn't also do it simultaneously
LOGGING_IN_SESSION = False
