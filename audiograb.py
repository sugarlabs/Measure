#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2009,10 Walter Bender
#    Copyright (C) 2009, Benjamin Berg, Sebastian Berg
#    Copyright (C) 2009, Sayamindu Dasgupta
#    Copyright (C) 2010, Sascha Silbe
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
from numpy import fromstring
import os
import subprocess
from string import find
from threading import Timer

from config import RATE, BIAS, DC_MODE_ENABLE, CAPTURE_GAIN, MIC_BOOST,\
                   SOUND_MAX_WAVE_LOGS, QUIT_MIC_BOOST, QUIT_DC_MODE_ENABLE,\
                   QUIT_CAPTURE_GAIN, QUIT_BIAS, DISPLAY_DUTY_CYCLE, XO1

import logging

log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)
logging.basicConfig()

SENSOR_AC_NO_BIAS = 'external'
SENSOR_AC_BIAS = 'sound'
SENSOR_DC_NO_BIAS = 'voltage'
SENSOR_DC_BIAS = 'resistance'


class AudioGrab:
    """ The interface between measure and the audio device """

    def __init__(self, callable1, activity):
        """ Initialize the class: callable1 is a data buffer;
            activity is the parent class"""

        self.callable1 = callable1
        self.activity = activity
        self.sensor = None

        self.temp_buffer = [0]
        self.picture_buffer = [] # place to hold screen grabs

        self.draw_graph_status = False
        self.screenshot = True

        self.rate = 48000
        self.final_count = 0
        self.count_temp = 0
        self.entry_count = 0

        self.waveform_id = 1
        self.logging_state = False
        self.buffer_interval_logging = 0

        self.counter_buffer = 0

        self._dc_control = None
        self._mic_bias_control = None
        self._capture_control = None
        self._mic_boost_control = None
        self._hardwired = False # Query controls or use hardwired names
        self._display_value = DISPLAY_DUTY_CYCLE

        # Set up gst pipeline
        self.pipeline = gst.Pipeline("pipeline")
        self.alsasrc = gst.element_factory_make("alsasrc", "alsa-source")
        self.pipeline.add(self.alsasrc)
        self.caps1 = gst.element_factory_make("capsfilter", "caps1")
        self.pipeline.add(self.caps1)
        caps_str = "audio/x-raw-int,rate=%d,channels=1,depth=16" % \
                  (RATE)
        self.caps1.set_property("caps", gst.caps_from_string(caps_str))
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
        try: # F11+
            log.debug('controls: %r', [t.props.untranslated_label \
                                       for t in self._mixer.list_tracks()])
            self._dc_control = self._find_control(['dc mode'])
            self._mic_bias_control = self._find_control(['mic bias',
                                                         'dc input bias',
                                                         'v_refout'])
            if self._mic_bias_control is not None:
                log.debug("Mic Bias is %s" % (
                        self._mic_bias_control.props.untranslated_label))
                log.debug("Min %s" % (str(self._mic_bias_control.min_volume)))
                log.debug("Max %s" % (str(self._mic_bias_control.max_volume)))
                log.debug("Channels %s" % (
                        str(self._mic_bias_control.num_channels)))
            self._mic_boost_control = self._find_control(['mic boost',
                                                          'mic boost (+20db)',
                                                          'internal mic boost',
                                                          'analog mic boost'])
            if self._mic_boost_control is not None:
                log.debug("Mic Boost is %s" % (
                        self._mic_boost_control.props.untranslated_label))
                log.debug("Min %s" % (str(self._mic_boost_control.min_volume)))
                log.debug("Max %s" % (str(self._mic_boost_control.max_volume)))
                log.debug("Channels %s" % (
                        str(self._mic_boost_control.num_channels)))

            self._mic_gain_control = self._find_control(['mic'])
            self._capture_control = self._find_control(['capture'])
            if self._capture_control is not None:
                log.debug("Capture is %s" % (
                        self._capture_control.props.untranslated_label))
                log.debug("Min %s" % (str(self._capture_control.min_volume)))
                log.debug("Max %s" % (str(self._capture_control.max_volume)))
                log.debug("Channels %s" % (
                        str(self._capture_control.num_channels)))
            self._master_control = self._find_control(['master'])
        except AttributeError: # F9- (no untranslated_label attribute)
            self._hardwired = True

        # Variables for saving and resuming state of sound device
        self.master = self.get_master()
        self.bias = BIAS
        self.dcmode = DC_MODE_ENABLE
        self.capture_gain = CAPTURE_GAIN
        self.mic_boost = MIC_BOOST
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
        temp_buffer = fromstring(buffer, 'int16')
        if not self.dont_queue_the_buffer:
            self._new_buffer(temp_buffer)
        else:
            pass
        if self.logging_state:
            if self.waveform_id == SOUND_MAX_WAVE_LOGS:
                self.waveform_id = 1
                self.logging_state = False
                self.activity.ji.stop_session()
            else:
                if self.capture_interval_sample or\
                   self.buffer_interval_logging == 0:
                    self._emit_for_logging(temp_buffer)
                    self.capture_interval_sample = False
            # If an immediate record is to be written, that's all
            # for the logging session
            if self.buffer_interval_logging == 0:
                self.logging_state = False
                self.activity.ji.stop_session()
                self.waveform_id = 1
        if self.activity.CONTEXT == 'sensor' and not self.logging_state:
            if self._display_value == 0: # Display value at DISPLAY_DUTY_CYCLE
                self.sensor.set_sample_value(str(temp_buffer[0]))
                self._display_value = DISPLAY_DUTY_CYCLE
            else:
                self._display_value -= 1
        return False

    def set_freeze_the_display(self, freeze=False):
        """Useful when just the display is needed to be frozen, but logging
        should continue"""
        self.dont_queue_the_buffer = not freeze

    def get_freeze_the_display(self):
        """Returns state of queueing the buffer"""
        return not self.dont_queue_the_buffer

    def set_sensor(self, sensor):
        """Keep a reference to the sensot toolbar for logging"""
        self.sensor = sensor

    def _emit_for_logging(self, buf):
        """Sends the data for logging"""
        if self.buffer_interval_logging == 0:
            self.activity.ji.take_screenshot()
        else:
            if self.screenshot:
                self.activity.ji.take_screenshot(self.waveform_id)
                self.waveform_id += 1
            else:
                # save value to Journal
                self.activity.ji.write_value(buf[0])
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
        self.capture_timer = Timer(self.buffer_interval_logging,
                                   self.sample_now)
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

    def reset_counter_buffer(self):
        """Resets the counter buffer used to keep track of after how many
        buffers to emit a buffer for logging"""
        self.counter_buffer = 0

    def set_sampling_rate(self, sr):
        """Sets the sampling rate of the capture device
        Sampling rate must be given as an integer for example 16000 for
        setting 16Khz sampling rate
        The sampling rate would be set in the device to the nearest available"""
        self.pause_grabbing()
        caps_str = "audio/x-raw-int,rate=%d,channels=1,depth=16" % (sr, )
        self.caps1.set_property("caps", gst.caps_from_string(caps_str))
        self.resume_grabbing()

    def get_sampling_rate(self):
        """Gets the sampling rate of the capture device"""
        return int(self.caps1.get_property("caps")[0]['rate'])

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
        """Not used ???"""
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
                [len(label) - len(p) for p in prefixes if label.startswith(p)]
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
            log.debug("found control: %s" %\
                          (str(controls[0][0].props.untranslated_label)))
            return controls[0][0]

        return None

    def save_state(self):
        """Saves the state of all audio controls"""
        log.debug("====================================")
        log.debug("Save state")
        self.master = self.get_master()
        self.bias = self.get_bias()
        self.dcmode = self.get_dc_mode()
        self.capture_gain = self.get_capture_gain()
        self.mic_boost = self.get_mic_boost()
        log.debug("====================================")

    def resume_state(self):
        """Put back all audio control settings from the saved state"""
        log.debug("====================================")
        log.debug("Resume state")
        self.set_master(self.master)
        self.set_bias(self.bias)
        self.set_dc_mode(self.dcmode)
        self.set_capture_gain(self.capture_gain)
        self.set_mic_boost(self.mic_boost)
        log.debug("====================================")

        """
        self.set_PCM_gain(self.PCM )
        self.set_mic_gain(self.mic)
        """

    def _get_mute(self, control, name, default):
        """Get mute status of a control"""
        if not control:
            log.warning('No %s control, returning constant mute status', name)
            return default

        value = bool(control.flags & gst.interfaces.MIXER_TRACK_MUTE)
        log.debug('Getting %s (%s) mute status: %r', name,
                  control.props.untranslated_label, value)
        return value

    def _set_mute(self, control, name, value):
        """Mute a control"""
        if not control:
            log.warning('No %s control, not setting mute', name)
            return

        self._mixer.set_mute(control, value)
        log.debug('Set mute for %s (%s) to %r', name,
                  control.props.untranslated_label, value)

    def _get_volume(self, control, name):
        """Get volume of a control and convert to a scale of 0-100"""
        if not control:
            log.warning('No %s control, returning constant volume', name)
            return 100

        try: # sometimes get_volume does not return a tuple
            hw_volume = self._mixer.get_volume(control)[0]
        except IndexError:
            log.warning('_get_volume: %s (%d-%d) %d channels' % (
                    control.props.untranslated_label, control.min_volume,
                    control.max_volume, control.num_channels))
            return 100

        min_vol = control.min_volume
        max_vol = control.max_volume
        percent = (hw_volume - min_vol)*100//(max_vol - min_vol)
        log.debug('Getting %s (%s) volume: %d (%d)', name,
            control.props.untranslated_label, percent, hw_volume)
        return percent

    def _set_volume(self, control, name, value):
        """Sets the level of a control on a scale of 0-100"""
        if not control:
            log.warning('No %s control, not setting volume', name)
            return

        # convert value to scale of control
        min_vol = control.min_volume
        max_vol = control.max_volume
        if min_vol != max_vol:
            hw_volume = value*(max_vol - min_vol)//100 + min_vol
            self._mixer.set_volume(control, (hw_volume,)*control.num_channels)
            log.debug('Set volume of %s (%s) to %d (%d)', name,
                      control.props.untranslated_label, value, hw_volume)
        else:
            log.warning('_set_volume: %s (%d-%d) %d channels' % (
                    control.props.untranslated_label, control.min_volume,
                    control.max_volume, control.num_channels))

    def amixer_set(self, control, state):
        """ Direct call to amixer for old systems. """
        if state:
            os.system("amixer set '%s' unmute" % (control))
        else:
            os.system("amixer set '%s' mute" % (control))

    def mute_master(self):
        """Mutes the Master Control"""
        if not self._hardwired and self.activity.hw != XO1:
            self._set_mute(self._master_control, 'Master', True)
        else:
            self.amixer_set('Master', False)

    def unmute_master(self):
        """Unmutes the Master Control"""
        if not self._hardwired and self.activity.hw != XO1:
            self._set_mute(self._master_control, 'Master', True)
        else:
            self.amixer_set('Master', True)

    def set_master(self, master_val):
        """Sets the Master gain slider settings
        master_val must be given as an integer between 0 and 100 indicating the
        percentage of the slider to be set"""
        if not self._hardwired:
            self._set_volume(self._master_control, 'Master', master_val)
        else:
            os.system("amixer set Master " + str(master_val) + "%")

    def get_master(self):
        """Gets the Master gain slider settings. The value returned is an
        integer between 0-100 and is an indicative of the percentage 0 - 100%"""
        if not self._hardwired:
            return self._get_volume(self._master_control, 'master')
        else:
            p = str(subprocess.Popen(["amixer", "get", "Master"],
                                     stdout=subprocess.PIPE).communicate()[0])
            p = p[find(p, "Front Left:"):]
            p = p[find(p, "[")+1:]
            p = p[:find(p, "%]")]
            return int(p)

    def set_bias(self, bias_state=False):
        """Enables / disables bias voltage."""
        if not self._hardwired and self.activity.hw != XO1:
            if self._mic_bias_control is None:
                return
            # if not isinstance(self._mic_bias_control,
            #              gst.interfaces.MixerOptions):
            if self._mic_bias_control not in self._mixer.list_tracks():
                log.warning("set_bias: not in mixer")
                return self._set_mute(self._mic_bias_control, 'Mic Bias',
                                      not bias_state)

            #values = self._mic_bias_control.get_values()
            # We assume that values are sorted from lowest (=off) to highest.
            # Since they are mixed strings ("Off", "50%", etc.), we cannot
            # easily ensure this by sorting with the default sort order.
            log.debug("set bias max is %s" % (str(
                        self._mic_bias_control.max_volume)))
            try:
                if bias_state:
                    # self._mixer.set_option(self._mic_bias_control, values[-1])
                    self._mixer.set_volume(self._mic_bias_control,
                                           self._mic_bias_control.max_volume)
                else:
                    self._mixer.set_volume(self._mic_bias_control,
                                           self._mic_bias_control.min_volume)
                    # self._mixer.set_option(self._mic_bias_control, values[0])
            except TypeError:
                log.warning('set_bias: %s (%d-%d) %d channels' % (
                    self._mic_bias_control.props.untranslated_label,
                    self._mic_bias_control.min_volume,
                    self._mic_bias_control.max_volume,
                    self._mic_bias_control.num_channels))
                self._set_mute(self._mic_bias_control, 'Mic Bias',
                               not bias_state)
        elif self._hardwired:
            self.amixer_set('V_REFOUT Enable', bias_state)
        else:
            self.amixer_set('MIC Bias Enable', bias_state)

    def get_bias(self):
        """Check whether bias voltage is enabled."""
        if not self._hardwired:
            if self._mic_bias_control is None:
                return False
            if self._mic_bias_control not in self._mixer.list_tracks():
                #              gst.interfaces.MixerOptions):
                log.warning("get_bias: not in mixer")
                return not self._get_mute(self._mic_bias_control, 'Mic Bias',
                                          False)
            #values = self._mic_bias_control.get_option()
            #values = self._mic_bias_control.get_values()
            log.warning('get_bias: %s (%d-%d) %d channels' % (
                    self._mic_bias_control.props.untranslated_label,
                    self._mic_bias_control.min_volume,
                    self._mic_bias_control.max_volume,
                    self._mic_bias_control.num_channels))
            current = self._mixer.get_volume(self._mic_bias_control)
            # same ordering assertion as in set_bias() applies
            # if current == values[0]:
            log.debug('current: %s' % (str(current)))
            if current == self._mic_bias_control.min_volume:
                return False
            return True
        else:
            p = str(subprocess.Popen(["amixer", "get", "'V_REFOUT Enable'"],
                                     stdout=subprocess.PIPE).communicate()[0])
            p = p[find(p, "Mono:"):]
            p = p[find(p, "[")+1:]
            p = p[:find(p, "]")]
            if p == "on":
                return True
            return False

    def set_dc_mode(self, dc_mode=False):
        """Sets the DC Mode Enable control
        pass False to mute and True to unmute"""
        if not self._hardwired and self.activity.hw != XO1:
            if self._dc_control is not None:
                self._set_mute(self._dc_control, 'DC mode', not dc_mode)
        else:
            self.amixer_set('DC Mode Enable', dc_mode)

    def get_dc_mode(self):
        """Returns the setting of DC Mode Enable control
        i .e. True: Unmuted and False: Muted"""
        if not self._hardwired:
            if self._dc_control is not None:
                return not self._get_mute(self._dc_control, 'DC mode', False)
            else:
                return False
        else:
            p = str(subprocess.Popen(["amixer", "get", "'DC Mode Enable'"],
                                     stdout=subprocess.PIPE).communicate()[0])
            p = p[find(p, "Mono:"):]
            p = p[find(p, "[")+1:]
            p = p[:find(p, "]")]
            if p == "on":
                return True
            else:
                return False

    def set_mic_boost(self, mic_boost=False):
        """Set Mic Boost.
        True = +20dB, False = 0dB"""
        if not self._hardwired:
            if self._mic_boost_control is None:
                return
            if self._mic_boost_control not in self._mixer.list_tracks():
                #              gst.interfaces.MixerOptions):
                log.warning("set_mic_boost not in mixer %s" %\
                                  (str(self._mic_boost_control)))
                return self._set_mute(self._mic_boost_control, 'Mic Boost',
                                      mic_boost)
            #values = self._mic_boost_control.get_values()
            value = self._mixer.get_volume(self._mic_boost_control)
            """
            if '20dB' not in values or '0dB' not in values:
                logging.error("Mic Boost (%s) is an option list, but doesn't "
                              "contain 0dB and 20dB settings",
                              self._mic_boost_control.props.label)
                return
            """
            try:
                if mic_boost:
                    # self._mixer.set_option(self._mic_boost_control, '20dB')
                    self._mixer.set_volume(self._mic_boost_control,
                                           self._mic_boost_control.max_volume)
                else:
                    # self._mixer.set_option(self._mic_boost_control, '0dB')
                    self._mixer.set_volume(self._mic_boost_control,
                                           self._mic_boost_control.min_volume)
            except TypeError:
                log.warning('set_mic_boost: %s (%d-%d) %d channels' % (
                    self._mic_boost_control.props.untranslated_label,
                    self._mic_boost_control.min_volume,
                    self._mic_boost_control.max_volume,
                    self._mic_boost_control.num_channels))
                return self._set_mute(self._mic_boost_control, 'Mic Boost',
                                      not mic_boost)
        else:
            self.amixer_set('Mic Boost (+20dB)', mic_boost)

    def get_mic_boost(self):
        """Return Mic Boost setting.
        True = +20dB, False = 0dB"""
        if not self._hardwired:
            if self._mic_boost_control is None:
                return False
            if self._mic_boost_control not in self._mixer.list_tracks():
                logging.error("get_mic_boost not found in mixer %s" %\
                                  (str(self._mic_boost_control)))
                return self._get_mute(self._mic_boost_control, 'Mic Boost',
                                      False)
            #values = self._mic_boost_control.get_values()
            # values = self._mixer.get_option(self._mic_boost_control)
            """
            if '20dB' not in values or '0dB' not in values:
                logging.error("Mic Boost (%s) is an option list, but doesn't "
                              "contain 0dB and 20dB settings",
                              self._mic_boost_control.props.label)
                return False
            """
            log.warning('get_mic_boost: %s (%d-%d) %d channels' % (
                    self._mic_boost_control.props.untranslated_label,
                    self._mic_boost_control.min_volume,
                    self._mic_boost_control.max_volume,
                    self._mic_boost_control.num_channels))
            current = self._mixer.get_volume(self._mic_boost_control)
            log.debug('current: %s' % (str(current)))
            # if current == '20dB':
            if current != self._mic_boost_control.min_volume:
                return True
            return False
        else:
            p = str(subprocess.Popen(["amixer", "get", "'Mic Boost (+20dB)'"],
                                     stdout=subprocess.PIPE).communicate()[0])
            p = p[find(p, "Mono:"):]
            p = p[find(p, "[")+1:]
            p = p[:find(p, "]")]
            if p == "on":
                return True
            else:
                return False

    def set_capture_gain(self, capture_val):
        """Sets the Capture gain slider settings
        capture_val must be given as an integer between 0 and 100 indicating the
        percentage of the slider to be set"""
        if not self._hardwired and self.activity.hw != XO1:
            if self._capture_control is not None:
                self._set_volume(self._capture_control, 'Capture', capture_val)
        else:
            os.system("amixer set Capture " + str(capture_val) + "%")

    def get_capture_gain(self):
        """Gets the Capture gain slider settings. The value returned is an
        integer between 0-100 and is an indicative of the percentage 0 - 100%"""
        if not self._hardwired:
            if self._capture_control is not None:
                return self._get_volume(self._capture_control, 'Capture')
            else:
                return 0
        else:
            p = str(subprocess.Popen(["amixer", "get", "Capture"],
                                     stdout=subprocess.PIPE).communicate()[0])
            p = p[find(p, "Front Left:"):]
            p = p[find(p, "[")+1:]
            p = p[:find(p, "%]")]
            return int(p)

    def set_mic_gain(self, mic_val):
        """Sets the MIC gain slider settings
        mic_val must be given as an integer between 0 and 100 indicating the
        percentage of the slider to be set"""
        if not self._hardwired and self.activity.hw != XO1:
            self._set_volume(self._mic_gain_control, 'Mic', mic_val)
        else:
            os.system("amixer set Mic " + str(mic_val) + "%")

    def get_mic_gain(self):
        """Gets the MIC gain slider settings. The value returned is an
        integer between 0-100 and is an indicative of the percentage 0 - 100%"""
        if not self._hardwired:
            return self._get_volume(self._mic_gain_control, 'Mic')
        else:
            p = str(subprocess.Popen(["amixer", "get", "Mic"],
                                     stdout=subprocess.PIPE).communicate()[0])
            try:
                p = p[find(p, "Mono:"):]
                p = p[find(p, "[")+1:]
                p = p[:find(p, "%]")]
                return int(p)
            except:
                return(0)

    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        """Set the type of sensor you want to use. Set sensor_type according
        to the following
        SENSOR_AC_NO_BIAS - AC coupling with Bias Off --> Very rarely used.
            Use when connecting a dynamic microphone externally
        SENSOR_AC_BIAS - AC coupling with Bias On --> The default settings.
            The internal MIC uses these
        SENSOR_DC_NO_BIAS - DC coupling with Bias Off --> measuring voltage
            output sensor. For example LM35 which gives output proportional
            to temperature
        SENSOR_DC_BIAS - DC coupling with Bias On --> measuing resistance.
        """
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (False, False, 50, True),
            SENSOR_AC_BIAS: (False, True, 40, True),
            SENSOR_DC_NO_BIAS: (True, False, 0, False),
            SENSOR_DC_BIAS: (True, True, 0, False)
        }
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        log.debug("====================================")
        log.debug("Set Sensor Type to %s" % (str(sensor_type)))
        self._set_sensor_type(mode, bias, gain, boost)
        log.debug("====================================")

    def _set_sensor_type(self, mode=None, bias=None, gain=None, boost=None):
        """Helper to modify (some) of the sensor settings."""
        if mode is not None:
            self.set_dc_mode(mode)
            if self._dc_control is not None:
                os.system("amixer get '%s'" %\
                              (self._dc_control.props.untranslated_label))
        if bias is not None:
            self.set_bias(bias)
            if self._mic_bias_control is not None:
                os.system("amixer get '%s'" %\
                              (self._mic_bias_control.props.untranslated_label))
        if gain is not None:
            self.set_capture_gain(gain)
            if self._capture_control is not None:
                os.system("amixer get '%s'" %\
                              (self._capture_control.props.untranslated_label))
        if boost is not None:
            self.set_mic_boost(boost)
            if self._mic_boost_control is not None:
                os.system("amixer get '%s'" %\
                             (self._mic_boost_control.props.untranslated_label))

    def on_activity_quit(self):
        """When Activity quits"""
        log.debug("====================================")
        log.debug("Quitting")
        self.set_mic_boost(QUIT_MIC_BOOST)
        self.set_dc_mode(QUIT_DC_MODE_ENABLE)
        self.set_capture_gain(QUIT_CAPTURE_GAIN)
        self.set_bias(QUIT_BIAS)
        # quit_PCM???
        self.stop_sound_device()
        if self.logging_state:
            self.activity.ji.stop_session()
        log.debug("====================================")


class AudioGrab_XO1(AudioGrab):
    """ Use default parameters for OLPC XO 1.0 laptop """
    pass


class AudioGrab_XO15(AudioGrab):
    """ Override parameters for OLPC XO 1.5 laptop """
    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        """Helper to modify (some) of the sensor settings."""
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (False, False, 80, True),
            SENSOR_AC_BIAS: (False, True, 80, True),
            SENSOR_DC_NO_BIAS: (True, False, 80, False),
            SENSOR_DC_BIAS: (True, True, 90, False)
        }
        log.debug("====================================")
        log.debug("Set Sensor Type to %s" % (str(sensor_type)))
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        self._set_sensor_type(mode, bias, gain, boost)
        log.debug("====================================")


class AudioGrab_Unknown(AudioGrab):
    """ Override parameters for generic hardware """
    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        """Helper to modify (some) of the sensor settings."""
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (None, False, 50, True),
            SENSOR_AC_BIAS: (None, True, 40, True),
            SENSOR_DC_NO_BIAS: (True, False, 80, False),
            SENSOR_DC_BIAS: (True, True, 90, False)
        }
        log.debug("====================================")
        log.debug("Set Sensor Type to %s" % (str(sensor_type)))
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        self._set_sensor_type(mode, bias, gain, boost)
        log.debug("====================================")
