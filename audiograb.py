#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2009, Walter Bender
#    Copyright (C) 2009, Benjamin Berg, Sebastian Berg
#    Copyright (C) 2009, Sayamindu Dasgupta
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

import pygst
pygst.require("0.10")
import gst
import gst.interfaces
import numpy as np
import time
import config
from threading import Timer

# Initialize logging.
import logging
log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)
logging.basicConfig()

SENSOR_AC_NO_BIAS = 0
SENSOR_AC_BIAS = 1
SENSOR_DC_NO_BIAS = 2
SENSOR_DC_BIAS = 3

class AudioGrab:
    """ The interface between measure and the audio device """

    def __init__(self, callable1, journal):
        """ Initialize the class: callable1 is a data buffer; 
            journal is used for logging """
        self.callable1 = callable1
        self.ji = journal
        self.sensor = None

        self.temp_buffer = [0]
        self.picture_buffer = [] # place to hold screen grabs

        self.draw_graph_status = False
        self.f = None
        self.logging_status = False
        self.screenshot = True

        self.rate = 48000		
        self.final_count = 0
        self.count_temp = 0
        self.entry_count = 0

        self.waveform_id = 1
        self.logging_state = False
        self.buffer_interval_logging = 0
        
        # Set up gst pipeline
        self.pipeline = gst.Pipeline("pipeline")
        self.alsasrc = gst.element_factory_make("alsasrc", "alsa-source")
        self.pipeline.add(self.alsasrc)
        self.caps1 = gst.element_factory_make("capsfilter", "caps1")
        self.pipeline.add(self.caps1)
        caps_str = "audio/x-raw-int,rate=%d,channels=1,depth=16" % \
                  (config.RATE)
        self.caps1.set_property("caps", gst.caps_from_string(caps_str) )
        self.fakesink = gst.element_factory_make("fakesink", "fsink")
        self.pipeline.add(self.fakesink)		
        self.fakesink.connect("handoff", self.on_buffer)	
        self.fakesink.set_property("signal-handoffs", True) 
        gst.element_link_many(self.alsasrc, self.caps1, self.fakesink)
        self.dont_queue_the_buffer = False

        self._mixer = gst.element_factory_make('alsamixer')
        rc = self._mixer.set_state(gst.STATE_PAUSED)
        assert rc == gst.STATE_CHANGE_SUCCESS

        # Query the available controls
        log.debug('controls: %r', [t.props.untranslated_label \
                                   for t in self._mixer.list_tracks()])
        self._dc_control = self._find_control(['dc mode'])
        self._mic_bias_control = self._find_control(['mic bias',
                                     'dc input bias', 'V_REFOUT'])
        self._mic_boost_control = self._find_control(['mic boost',
                                     'analog mic boost'])
        self._mic_gain_control = self._find_control(['mic'])
        self._capture_control = self._find_control(['capture'])
        self._master_control = self._find_control(['master'])

        # Variables for saving and resuming state of sound device
        self.master  = self.get_master()
        self.bias = config.BIAS
        self.dcmode =  config.DC_MODE_ENABLE
        self.capture_gain  = config.CAPTURE_GAIN
        self.mic_boost = config.MIC_BOOST
        self.mic = self.get_mic_gain()

        # Timer for interval sampling and switch to indicate when to capture
        self.capture_timer = None
        self.capture_interval_sample = False

    def set_handoff_signal(self, handoff_state):
        """Sets whether the handoff signal would generate an interrupt or not"""
        self.fakesink.set_property("signal-handoffs", handoff_state)

    def _new_buffer(self, buf):
        """ Use a new buffer """
        if not self.dont_queue_the_buffer:
            self.temp_buffer = buf
            self.callable1(buf)
        else:
            pass

    def on_buffer(self, element, buffer, pad):		
        """The function that is called whenever new data is available
        This is the signal handler for the handoff signal"""
        temp_buffer = np.fromstring(buffer, 'int16')
        if not self.dont_queue_the_buffer:
            self._new_buffer(temp_buffer)
        else:
            pass
        if self.logging_state:
            if self.waveform_id == config.SOUND_MAX_WAVE_LOGS:
                self.waveform_id = 1
                self.logging_state = False
                self.ji.stop_session()
            else:
                if self.capture_interval_sample  or self.buffer_interval_logging == 0:
                    self._emit_for_logging(temp_buffer)
                    self.capture_interval_sample = False
            # If an immediate record is to be written, that's all 
            # for the logging session
            if self.buffer_interval_logging == 0:
                self.logging_state = False
                self.ji.stop_session()
                self.waveform_id = 1
        return False

    def set_freeze_the_display(self, freeze=False):
        """Useful when just the display is needed to be frozen, but logging 
        should continue"""
        self.dont_queue_the_buffer = not freeze

    def get_freeze_the_display(self):
        """Returns state of queueing the buffer"""
        return not self.dont_queue_the_buffer

    def set_sensor(self, sensor):
        self.sensor = sensor

    def _emit_for_logging(self, buf):
        """Sends the data for logging"""
        if self.buffer_interval_logging == 0:
            self.ji.take_screenshot()
        else:
            if self.screenshot == True:
                self.ji.take_screenshot(self.waveform_id)
                self.waveform_id+=1
            else:
                # save value to Journal
                self.ji.write_value(buf[0])
                # display value on Sensor toolbar
                self.sensor.set_sample_value(str(buf[0]))

    def start_sound_device(self):
        """Start or Restart grabbing data from the audio capture"""
        gst.event_new_flush_start()
        self.pipeline.set_state(gst.STATE_PLAYING)

    def stop_sound_device(self):
        """Stop grabbing data from capture device"""
        gst.event_new_flush_stop()
        self.pipeline.set_state(gst.STATE_NULL)

    def set_logging_params(self, start_stop=False, interval=0, screenshot=True):
        """Configures for logging of data i.e. starts or stops a session
        Sets an interval if logging interval is to be started
        Sets if screenshot of waveform is to be taken or values need to be 
        written"""
        self.logging_state = start_stop
        self.set_buffer_interval_logging(interval)
        if not start_stop:
            if self.capture_timer:
                self.capture_timer.cancel()
                self.capture_timer = None
                self.capture_interval_sample = False
        elif interval != 0:
            self.make_timer()
        self.screenshot = screenshot

    def sample_now(self):
        """ Log the current sample now. This method is called from the
        capture_timer object when the interval expires. """
        self.capture_interval_sample = True
        self.make_timer()

    def make_timer(self):
        """ Create the next timer that will go off at the proper interval.
        This is used when the user has selected a sampling interval > 0
        and the logging_state is True. """
        self.capture_timer = Timer(self.buffer_interval_logging, self.sample_now)
        self.capture_timer.start()
   
    def take_picture(self):
        """Used to grab and temporarily store the current buffer"""
        self.picture_buffer = self.temp_buffer.copy()

    def set_logging_state(self, start_stop=False):
        """Sets whether buffer is to be emited for logging (True) or not
        (False)"""
        self.logging_state = start_stop

    def set_buffer_interval_logging(self, interval=0):
        """Sets the number of buffers after which a buffer needs to be
        emitted"""
        self.buffer_interval_logging = interval

    def set_sampling_rate(self, sr):
        """Sets the sampling rate of the capture device
        Sampling rate must be given as an integer for example 16000 for
        setting 16Khz sampling rate
        The sampling rate would be set in the device to the nearest available"""
        self.pause_grabbing()
        caps_str = "audio/x-raw-int,rate=%d,channels=1,depth=16" % (sr, )
        self.caps1.set_property("caps", gst.caps_from_string(caps_str) )
        self.resume_grabbing()

    def get_sampling_rate(self):
        """Gets the sampling rate of the capture device"""
        return int(self.caps1.get_property("caps")[0]['rate'] )

    def set_callable1(self, callable1):
        """Sets the callable to the drawing function for giving the
        data at the end of idle-add"""
        self.callable1 = callable1

    def start_grabbing(self):
        """Called right at the start of the Activity"""
        self.start_sound_device()

    def pause_grabbing(self):
        """When Activity goes into background"""
        self.save_state()
        self.stop_sound_device()

    def resume_grabbing(self):
        """When Activity becomes active after going to background"""
        self.start_sound_device()
        self.resume_state()
   
    def stop_grabbing(self):
        self.stop_sound_device()
        self.set_handoff_signal(False)

    def _find_control(self, prefixes):
        """Try to find a mixer control matching one of the prefixes.

        The control with the best match (smallest difference in length
        between label and prefix) will be returned. If no match is found,
        None is returned.
        """
        def best_prefix(label, prefixes):
            matches =\
                [len(label)-len(p) for p in prefixes if label.startswith(p)]
            if not matches:
                return None

            matches.sort()
            return matches[0]

        controls = []
        for track in self._mixer.list_tracks():
            label = track.props.untranslated_label.lower()
            diff = best_prefix(label, prefixes)
            if diff is not None:
                controls.append((track, diff))

        controls.sort(key=lambda e: e[1])
        if controls:
            return controls[0][0]

        return None

    def save_state(self):
        """Saves the state of all audio controls"""
        self.master = self.get_master()
        self.bias = self.get_bias()
        self.dcmode =  self.get_dc_mode()
        self.capture_gain  = self.get_capture_gain()
        self.mic_boost = self.get_mic_boost()

    def resume_state(self):
        """Put back all audio control settings from the saved state"""
        self.set_master(self.master)
        self.set_bias(self.bias)
        self.set_dc_mode(self.dcmode)
        self.set_capture_gain(self.capture_gain)
        self.set_mic_boost(self.mic_boost)

    def _get_mute(self, control, name, default):
        if not control:
            log.warning('No %s control, returning constant mute status', name)
            return default

        value = bool(control.flags & gst.interfaces.MIXER_TRACK_MUTE)
        log.debug('Getting %s (%s) mute status: %r', name,
            control.props.untranslated_label, value)
        return value

    def _set_mute(self, control, name, value):
        if not control:
            log.warning('No %s control, not setting mute', name)
            return

        self._mixer.set_mute(control, value)
        log.debug('Set mute for %s (%s) to %r', name,
            control.props.untranslated_label, value)

    def _get_volume(self, control, name):
        if not control:
            log.warning('No %s control, returning constant volume', name)
            return 100

        try: # sometimes control is not None and yet it is not a tuple?
            hw_volume = self._mixer.get_volume(control)[0]
        except IndexError:
            log.debug('ERROR getting control %s', control)
            return 100

        min_vol = control.min_volume
        max_vol = control.max_volume
        percent = (hw_volume - min_vol)*100//(max_vol - min_vol)
        log.debug('Getting %s (%s) volume: %d (%d)', name,
            control.props.untranslated_label, percent, hw_volume)
        return percent

    def _set_volume(self, control, name, value):
        if not control:
            log.warning('No %s control, not setting volume', name)
            return

        min_vol = control.min_volume
        max_vol = control.max_volume
        hw_volume = value*(max_vol - min_vol)//100 + min_vol
        self._mixer.set_volume(control, (hw_volume,)*control.num_channels)
        log.debug('Set volume of %s (%s) to %d (%d)', name,
            control.props.untranslated_label, value, hw_volume)

    def mute_master(self):
        """Mutes the Master Control"""
        self._set_mute(self._master_control, 'Master', True)

    def unmute_master(self):
        """Unmutes the Master Control"""
        self._set_mute(self._master_control, 'Master', False)

    def set_master(self, master_val):
        """Sets the Master gain slider settings 
        master_val must be given as an integer between 0 and 100 indicating the
        percentage of the slider to be set"""
        self._set_volume(self._master_control, 'Master', master_val)

    def get_master(self):
        """Gets the Master gain slider settings. The value returned is an
        integer between 0-100 and is an indicative of the percentage 0 - 100%"""
        return self._get_volume(self._master_control, 'master')

    def set_bias(self,bias_state=False):
        """Enables / disables bias voltage. On XO-1.5 it uses the 80% setting.
        """
        if not isinstance(self._mic_bias_control, gst.interfaces.MixerOptions):
            return self._set_mute(self._mic_bias_control, 'Mic Bias', 
                                  not bias_state)

        values = self._mic_bias_control.get_values()
        # We assume that the values are sorted from lowest (=off) to highest.
        # Since they are mixed strings ("Off", "50%", etc.), we cannot easily
        # ensure this ourselves by sorting with the default sort order.
        if bias_state:
            self._mixer.set_option(self._mic_bias_control, values[-1])
        else:
            self._mixer.set_option(self._mic_bias_control, values[0])

    def get_bias(self):
        """Check whether bias voltage is enabled."""
        if not isinstance(self._mic_bias_control, gst.interfaces.MixerOptions):
            return not self._get_mute(self._mic_bias_control, 'Mic Bias', False)

        values = self._mic_bias_control.get_values()
        current = self._mixer.get_option(self._mic_bias_control)
        # same ordering assertion as in set_bias() applies
        if current == values[0]:
            return False

        return True

    def set_dc_mode(self, dc_mode = False):
        """Sets the DC Mode Enable control
        pass False to mute and True to unmute"""
        self._set_mute(self._dc_control, 'DC mode', not dc_mode)

    def get_dc_mode(self):
        """Returns the setting of DC Mode Enable control 
        i .e. True: Unmuted and False: Muted"""
        return not self._get_mute(self._dc_control, 'DC mode', False)

    def set_mic_boost(self, mic_boost=False):
        """Set Mic Boost.
        True = +20dB, False = 0dB"""
        if not isinstance(self._mic_boost_control, gst.interfaces.MixerOptions):
            return self._set_mute(self._mic_boost_control, 'Mic Boost',
                                  mic_boost)

        values = self._mic_boost_control.get_values()
        if '20dB' not in values or '0dB' not in values:
            logging.error("Mic Boost (%s) is an option list, but doesn't "
                "contain 0dB and 20dB settings", 
                self._mic_boost_control.props.label)
            return

        if mic_boost:
            self._mixer.set_option(self._mic_boost_control, '20dB')
        else:
            self._mixer.set_option(self._mic_boost_control, '0dB')

    def get_mic_boost(self):
        """Return Mic Boost setting.
        True = +20dB, False = 0dB"""
        if not isinstance(self._mic_boost_control, gst.interfaces.MixerOptions):
            return self._get_mute(self._mic_boost_control, 'Mic Boost', False)

        values = self._mic_boost_control.get_values()
        if '20dB' not in values or '0dB' not in values:
            logging.error("Mic Boost (%s) is an option list, but doesn't "
                "contain 0dB and 20dB settings", 
                self._mic_boost_control.props.label)
            return False

        current = self._mixer.get_option(self._mic_boost_control)
        if current == '20dB':
            return True

        return False

    def set_capture_gain(self, capture_val):
        """Sets the Capture gain slider settings 
        capture_val must be given as an integer between 0 and 100 indicating the
        percentage of the slider to be set"""
        self._set_volume(self._capture_control, 'Capture', capture_val)

    def get_capture_gain(self):
        """Gets the Capture gain slider settings. The value returned is an
        integer between 0-100 and is an indicative of the percentage 0 - 100%"""
        return self._get_volume(self._capture_control, 'Capture')

    def set_mic_gain(self, mic_val):
        """Sets the MIC gain slider settings
        mic_val must be given as an integer between 0 and 100 indicating the
        percentage of the slider to be set"""
        self._set_volume(self._mic_gain_control, 'Mic', mic_val)

    def get_mic_gain(self):
        """Gets the MIC gain slider settings. The value returned is an
        integer between 0-100 and is an indicative of the percentage 0 - 100%"""
        return self._get_volume(self._mic_gain_control, 'Mic')

    def mute_mic(self):
        """Mutes the Mic Control"""
        self._set_mute(self._mic_mute_control, 'Mic', True)

    def unmute_mic(self):
        """Unmutes the Mic Control"""
        self._set_mute(self._mic_mute_control, 'Mic', False)

    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        """Set the type of sensor you want to use. Set sensor_type according 
        to the following
        SENSOR_AC_NO_BIAS - AC coupling with Bias Off --> Very rarely used.
            Use when connecting a dynamic microphone externally
        SENSOR_AC_BIAS - AC coupling with Bias On --> The default settings. 
            The internal MIC uses these
        SENSOR_DC_NO_BIAS - DC coupling with Bias Off --> Used when using a voltage
            output sensor. For example LM35 which gives output proportional
            to temperature
        SENSOR_DC_BIAS - DC coupling with Bias On --> Used with resistive sensors.
            For example"""
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (False, False, 50, True),
            SENSOR_AC_BIAS: (False, True, 40, True),
            SENSOR_DC_NO_BIAS: (True, False, 0, False),
            SENSOR_DC_BIAS: (True, True, 0, False),
        }
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        self._set_sensor_type(mode, bias, gain, boost)

    def _set_sensor_type(self, mode=None, bias=None, gain=None, boost=None):
        """Helper to modify (some) of the sensor settings."""
        if mode is not None:
            self.set_dc_mode(mode)
        if bias is not None:
            self.set_bias(bias)
        if gain is not None:
            self.set_capture_gain(gain)
        if boost is not None:
            self.set_mic_boost(boost)

    def on_activity_quit(self):
        """When Activity quits"""
        self.set_mic_boost(config.QUIT_MIC_BOOST)
        self.set_dc_mode(config.QUIT_DC_MODE_ENABLE)
        self.set_capture_gain(config.QUIT_CAPTURE_GAIN)
        self.set_bias(config.QUIT_BIAS)
        self.stop_sound_device()


class AudioGrab_XO_1(AudioGrab):
    pass

class AudioGrab_XO_1_5(AudioGrab):
    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (False, False, 80, True),
            SENSOR_AC_BIAS: (False, True, 80, True),
            SENSOR_DC_NO_BIAS: (True, False, 0, False),
            SENSOR_DC_BIAS: (True, True, 0, False),
        }
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        self._set_sensor_type(mode, bias, gain, boost)

class AudioGrab_Unknown(AudioGrab):
    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (None, False, 50, True),
            SENSOR_AC_BIAS: (None, True, 40, True),
        }
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        self._set_sensor_type(mode, bias, gain, boost)
