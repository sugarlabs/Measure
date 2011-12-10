#! /usr/bin/python
#
# Author:  Arjun Sarwal   arjun@laptop.org
# Copyright (C) 2007, Arjun Sarwal
# Copyright (C) 2009-11 Walter Bender
# Copyright (C) 2009, Benjamin Berg, Sebastian Berg
# Copyright (C) 2009, Sayamindu Dasgupta
# Copyright (C) 2010, Sascha Silbe
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA


import pygst
pygst.require("0.10")
import gst
import gst.interfaces
from numpy import fromstring
import commands
import traceback
from string import find
from threading import Timer

from config import RATE, BIAS, DC_MODE_ENABLE, CAPTURE_GAIN, MIC_BOOST,\
                   SOUND_MAX_WAVE_LOGS, QUIT_MIC_BOOST, QUIT_DC_MODE_ENABLE,\
                   QUIT_CAPTURE_GAIN, QUIT_BIAS, DISPLAY_DUTY_CYCLE, XO1, \
                   XO15, XO175, MAX_GRAPHS

import logging

log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)
logging.basicConfig()


SENSOR_AC_NO_BIAS = 'external'
SENSOR_AC_BIAS = 'sound'
SENSOR_DC_NO_BIAS = 'voltage'
SENSOR_DC_BIAS = 'resistance'


def _avg(array, abs_value=False):
    ''' Calc. the average value of an array '''
    if len(array) == 0:
        return 0
    array_sum = 0
    if abs_value:
        for a in array:
            array_sum += abs(a)
    else:
        for a in array:
            array_sum += a
    return float(array_sum) / len(array)


class AudioGrab():
    """ The interface between measure and the audio device """

    def __init__(self, callable1, activity):
        """ Initialize the class: callable1 is a data buffer;
            activity is the parent class"""

        self.callable1 = callable1
        self.activity = activity
        self.sensor = None

        if self.activity.hw == XO1:
            self.voltage_gain = 0.00002225
            self.voltage_bias = 1.140
        elif self.activity.hw == XO15:
            self.voltage_gain = -0.0001471
            self.voltage_bias = 1.695
        else:  # FIXME: Calibrate 1.75
            self.voltage_gain = -0.0001471
            self.voltage_bias = 1.695

        self.temp_buffer = [0]
        self.picture_buffer = []  # place to hold screen grabs

        self.draw_graph_status = False
        self.screenshot = True
        self._debounce = True

        self.rate = RATE
        if self.activity.hw == XO1:
            self.channels = 1
        else:
            self.channels = None
        self.final_count = 0
        self.count_temp = 0
        self.entry_count = 0

        self.capture_counter = 1
        self.logging_state = False
        self.buffer_interval_logging = 0

        self.counter_buffer = 0

        self._dc_control = None
        self._mic_bias_control = None
        self._capture_control = None
        self._mic_boost_control = None
        self._labels_available = True  # Query controls for device names
        self._display_counter = DISPLAY_DUTY_CYCLE

        self._query_mixer()
        # If Channels was not found in the Capture controller, guess.
        if self.channels is None:
            log.warning('Guessing there are 2 channels')
            self.channels = 2
        self.activity.wave.set_channels(self.channels)

        # Set mixer to known state
        self.set_dc_mode(DC_MODE_ENABLE)
        self.set_bias(BIAS)
        self.set_capture_gain(CAPTURE_GAIN)
        self.set_mic_boost(MIC_BOOST)

        self.master = self.get_master()
        self.dc_mode = self.get_dc_mode()
        self.bias = self.get_bias()
        self.capture_gain = self.get_capture_gain()
        self.mic_boost = self.get_mic_boost()

        # Set up gstreamer pipeline
        self._pad_count = 0
        self.pads = []
        self.queue = []
        self.fakesink = []
        self.pipeline = gst.Pipeline('pipeline')
        self.alsasrc = gst.element_factory_make('alsasrc', 'alsa-source')
        self.pipeline.add(self.alsasrc)
        self.caps1 = gst.element_factory_make('capsfilter', 'caps1')
        self.pipeline.add(self.caps1)
        caps_str = 'audio/x-raw-int,rate=%d,channels=%d,depth=16' % (
            RATE, self.channels)
        self.caps1.set_property('caps', gst.caps_from_string(caps_str))
        if self.channels == 1:
            self.fakesink.append(gst.element_factory_make('fakesink', 'fsink'))
            self.pipeline.add(self.fakesink[0])
            self.fakesink[0].connect('handoff', self.on_buffer, 0)
            self.fakesink[0].set_property('signal-handoffs', True)
            gst.element_link_many(self.alsasrc, self.caps1, self.fakesink[0])
        else:
            if not hasattr(self, 'splitter'):
                self.splitter = gst.element_factory_make('deinterleave')
                self.pipeline.add(self.splitter)
                self.splitter.set_properties('keep-positions=true', 'name=d')
                self.splitter.connect('pad-added', self._splitter_pad_added)
                gst.element_link_many(self.alsasrc, self.caps1, self.splitter)
            for i in range(self.channels):
                self.queue.append(gst.element_factory_make('queue'))
                self.pipeline.add(self.queue[i])
                self.fakesink.append(gst.element_factory_make('fakesink'))
                self.pipeline.add(self.fakesink[i])
                self.fakesink[i].connect('handoff', self.on_buffer, i)
                self.fakesink[i].set_property('signal-handoffs', True)

        self.dont_queue_the_buffer = False

        # Timer for interval sampling and switch to indicate when to capture
        self.capture_timer = None
        self.capture_interval_sample = False

    def _query_mixer(self):
        self._mixer = gst.element_factory_make('alsamixer')
        rc = self._mixer.set_state(gst.STATE_PAUSED)
        assert rc == gst.STATE_CHANGE_SUCCESS

        # Query the available controls
        tracks_list = self._mixer.list_tracks()
        if hasattr(tracks_list[0].props, 'untranslated_label'):
            log.debug('Found controls for: %r', [t.props.untranslated_label \
                                       for t in tracks_list])
            self._capture_control = self._find_control(['capture', 'axi'])
            self._dc_control = self._find_control(['dc mode'])
            self._mic_bias_control = self._find_control(['mic bias',
                                                         'dc input bias',
                                                         'v_refout'])
            self._mic_boost_control = self._find_control(['mic boost',
                                                          'mic boost (+20db)',
                                                          'internal mic boost',
                                                          'analog mic boost'])
            self._mic_gain_control = self._find_control(['mic'])
            self._master_control = self._find_control(['master'])
        else:  # Use hardwired values
            log.warning('Cannot use mixer controls directly')
            self._labels_available = False

    def _unlink_sink_queues(self):
        ''' Build the sink pipelines '''

        # If there were existing pipelines, unlink them
        for i in range(self._pad_count):
            log.debug('unlinking old elements')
            try:
                self.splitter.unlink(self.queue[i])
                self.queue[i].unlink(self.fakesink[i])
            except:
                traceback.print_exc()

        # Build the new pipelines
        self._pad_count = 0
        self.pads = []
        log.debug('building new pipelines')

    def _splitter_pad_added(self, element, pad):
        ''' Seems to be the case that ring is right channel 0,
                                       tip is  left channel 1'''
        log.debug('splitter pad %d added' % (self._pad_count))
        self.pads.append(pad)
        if (self._pad_count < min(self.channels, MAX_GRAPHS)):
            pad.link(self.queue[self._pad_count].get_pad('sink'))
            self.queue[self._pad_count].get_pad('src').link(
                self.fakesink[self._pad_count].get_pad('sink'))
            self._pad_count += 1
        else:
            log.debug('ignoring channels > %d' % (min(self.channels,
                                                      MAX_GRAPHS)))

    def set_handoff_signal(self, handoff_state):
        '''Sets whether the handoff signal would generate an interrupt
        or not'''
        for i in range(len(self.fakesink)):
            self.fakesink[i].set_property('signal-handoffs', handoff_state)

    def _new_buffer(self, buf, channel):
        ''' Use a new buffer '''
        if not self.dont_queue_the_buffer:
            self.temp_buffer = buf
            self.callable1(buf, channel=channel)
        else:
            pass

    def on_buffer(self, element, data_buffer, pad, channel):
        '''The function that is called whenever new data is available
        This is the signal handler for the handoff signal'''
        temp_buffer = fromstring(data_buffer, 'int16')
        if not self.dont_queue_the_buffer:
            self._new_buffer(temp_buffer, channel=channel)

        if self.logging_state:
            # If we've hit the maximum no. of log files, stop.
            if self.capture_counter == SOUND_MAX_WAVE_LOGS:
                self.capture_counter = 1
                self.logging_state = False
                self.activity.data_logger.stop_session()
            else:
                if self.capture_interval_sample or \
                   self.buffer_interval_logging == 0:
                    self._emit_for_logging(temp_buffer, channel=channel)
                    self.capture_interval_sample = False

            # If an immediate record is to be written, end logging session
            if self.buffer_interval_logging == 0:
                self.logging_state = False
                self.activity.data_logger.stop_session()

        # In sensor mode, periodly update the textbox with a sample value
        if self.activity.CONTEXT == 'sensor' and not self.logging_state:
            # Only update display every nth time, where n=DISPLAY_DUTY_CYCLE
            if self._display_counter == 0:
                if self.activity.sensor_toolbar.mode == 'resistance':
                    self.sensor.set_sample_value(
                        self._calibrate_resistance(temp_buffer),
                        channel=channel)
                else:
                    self.sensor.set_sample_value(
                        self._calibrate_voltage(temp_buffer),
                        channel=channel)
                self._display_counter = DISPLAY_DUTY_CYCLE
            else:
                self._display_counter -= 1
        return False

    def _calibrate_resistance(self, data_buffer):
        ''' Return calibrated value for resistance '''
        # See <http://bugs.sugarlabs.org/ticket/552#comment:7>
        # TODO: test this calibration on XO 1.5, XO 1.75
        avg_buffer = _avg(data_buffer)
        if self.activity.hw == XO1:
            resistance = 2.718 ** ((avg_buffer * 0.000045788) + 8.0531)
        else:
            if avg_buffer > 0:
                return (420000000 / avg_buffer) - 13500
            else:
                return 420000000

    def _calibrate_voltage(self, data_buffer):
        ''' Return calibrated value for voltage '''
        # See <http://bugs.sugarlabs.org/ticket/552#comment:7>
        return _avg(data_buffer) * self.voltage_gain + self.voltage_bias

    def set_freeze_the_display(self, freeze=False):
        '''Useful when just the display is needed to be frozen, but logging
        should continue'''
        self.dont_queue_the_buffer = not freeze

    def get_freeze_the_display(self):
        '''Returns state of queueing the buffer'''
        return not self.dont_queue_the_buffer

    def set_sensor(self, sensor):
        '''Keep a reference to the sensot toolbar for logging'''
        self.sensor = sensor

    def _emit_for_logging(self, data_buffer, channel=0):
        '''Sends the data for logging'''
        if self.screenshot:
            if self._debounce:
                self._debounce = False
                if self.activity.data_logger.take_screenshot(
                    self.capture_counter):
                    self.capture_counter += 1
                else:
                    log.debug('failed to take screenshot %d' % (
                            self.capture_counter))
                self._debounce = True
        else:
            if self.activity.sensor_toolbar.mode == 'resistance':
                value = self._calibrate_resistance(data_buffer)
            else:
                value = self._calibrate_voltage(data_buffer)
            log.debug('logging value %f from channel %d' % (value, channel))
            self.activity.data_logger.write_value(
                '%d, %0.3f' % (channel, value))
            self.sensor.set_sample_value(value, channel=channel)

    def start_sound_device(self):
        '''Start or Restart grabbing data from the audio capture'''
        gst.event_new_flush_start()
        self.pipeline.set_state(gst.STATE_PLAYING)

    def stop_sound_device(self):
        '''Stop grabbing data from capture device'''
        gst.event_new_flush_stop()
        self.pipeline.set_state(gst.STATE_NULL)

    def set_logging_params(self, start_stop=False, interval=0,
                           screenshot=True):
        '''Configures for logging of data i.e. starts or stops a session
        Sets an interval if logging interval is to be started
        Sets if screenshot of waveform is to be taken or values need to be
        written'''
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
        ''' Log the current sample now. This method is called from the
        capture_timer object when the interval expires. '''
        self.capture_interval_sample = True
        self.make_timer()

    def make_timer(self):
        ''' Create the next timer that will go off at the proper interval.
        This is used when the user has selected a sampling interval > 0
        and the logging_state is True. '''
        self.capture_timer = Timer(self.buffer_interval_logging,
                                   self.sample_now)
        self.capture_timer.start()

    def take_picture(self):
        '''Used to grab and temporarily store the current buffer'''
        self.picture_buffer = self.temp_buffer.copy()

    def set_logging_state(self, start_stop=False):
        '''Sets whether buffer is to be emited for logging (True) or not
        (False)'''
        self.logging_state = start_stop

    def set_buffer_interval_logging(self, interval=0):
        '''Sets the number of buffers after which a buffer needs to be
        emitted'''
        self.buffer_interval_logging = interval

    def reset_counter_buffer(self):
        '''Resets the counter buffer used to keep track of after how many
        buffers to emit a buffer for logging'''
        self.counter_buffer = 0

    def set_sampling_rate(self, sr):
        '''Sets the sampling rate of the capture device Sampling rate
        must be given as an integer for example 16000 for setting
        16Khz sampling rate The sampling rate would be set in the
        device to the nearest available'''
        self.pause_grabbing()
        caps_str = 'audio/x-raw-int,rate=%d,channels=%d,depth=16' % (
            sr, self.channels)
        self.caps1.set_property('caps', gst.caps_from_string(caps_str))
        self.resume_grabbing()

    def get_sampling_rate(self):
        '''Gets the sampling rate of the capture device'''
        return int(self.caps1.get_property('caps')[0]['rate'])

    def set_callable1(self, callable1):
        '''Sets the callable to the drawing function for giving the
        data at the end of idle-add'''
        self.callable1 = callable1

    def start_grabbing(self):
        '''Called right at the start of the Activity'''
        self.start_sound_device()
        self.set_handoff_signal(True)

    def pause_grabbing(self):
        '''When Activity goes into background'''
        self.save_state()
        self.stop_sound_device()

    def resume_grabbing(self):
        '''When Activity becomes active after going to background'''
        self.start_sound_device()
        self.resume_state()
        self.set_handoff_signal(True)

    def stop_grabbing(self):
        '''Not used ???'''
        self.stop_sound_device()
        self.set_handoff_signal(False)

    def _find_control(self, prefixes):
        '''Try to find a mixer control matching one of the prefixes.

        The control with the best match (smallest difference in length
        between label and prefix) will be returned. If no match is found,
        None is returned.
        '''
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
            log.debug('Found control: %s' %\
                          (str(controls[0][0].props.untranslated_label)))

            if self.channels is None:
                if hasattr(controls[0][0], 'num_channels'):
                    channels = controls[0][0].num_channels
                    if channels > 0:
                        self.channels = channels
                        log.debug('setting channels to %d' % (self.channels))

            return controls[0][0]

        return None

    def save_state(self):
        '''Saves the state of all audio controls'''
        log.debug('Save state')
        self.master = self.get_master()
        self.bias = self.get_bias()
        self.dc_mode = self.get_dc_mode()
        self.capture_gain = self.get_capture_gain()
        self.mic_boost = self.get_mic_boost()

    def resume_state(self):
        '''Put back all audio control settings from the saved state'''
        log.debug('Resume state')
        self.set_master(self.master)
        self.set_bias(self.bias)
        self.set_dc_mode(self.dc_mode)
        self.set_capture_gain(self.capture_gain)
        self.set_mic_boost(self.mic_boost)

    def _get_mute(self, control, name, default):
        '''Get mute status of a control'''
        if not control:
            log.warning('No %s control, returning constant mute status', name)
            return default

        value = bool(control.flags & gst.interfaces.MIXER_TRACK_MUTE)
        log.debug('Getting %s (%s) mute status: %r', name,
                  control.props.untranslated_label, value)
        return value

    def _set_mute(self, control, name, value):
        '''Mute a control'''
        if not control:
            log.warning('No %s control, not setting mute', name)
            return

        self._mixer.set_mute(control, value)
        log.debug('Set mute for %s (%s) to %r', name,
                  control.props.untranslated_label, value)

    def _get_volume(self, control, name):
        '''Get volume of a control and convert to a scale of 0-100'''
        if not control:
            log.warning('No %s control, returning constant volume', name)
            return 100

        volume = self._mixer.get_volume(control)
        if type(volume) == tuple:
            hw_volume = volume[0]
        else:
            hw_volume = volume

        min_vol = control.min_volume
        max_vol = control.max_volume
        if max_vol == min_vol:
            percent = 100
        else:
            percent = (hw_volume - min_vol) * 100 // (max_vol - min_vol)
        log.debug('Getting %s (%s) volume: %d (%d)', name,
            control.props.untranslated_label, percent, hw_volume)
        return percent

    def _set_volume(self, control, name, value):
        '''Sets the level of a control on a scale of 0-100'''
        if not control:
            log.warning('No %s control, not setting volume', name)
            return

        # convert value to scale of control
        min_vol = control.min_volume
        max_vol = control.max_volume
        if min_vol != max_vol:
            hw_volume = value * (max_vol - min_vol) // 100 + min_vol
            self._mixer.set_volume(control,
                                   (hw_volume,) * control.num_channels)
        else:
            log.warning('_set_volume: %s (%d-%d) %d channels' % (
                    control.props.untranslated_label, control.min_volume,
                    control.max_volume, control.num_channels))

    def amixer_set(self, control, state):
        ''' Direct call to amixer for old systems. '''
        if state:
            (status, output) = commands.getstatusoutput(
                'amixer set "%s" unmute' % (control))
            if status != 0:
                log.warning('Problem with amixer set "%s" unmute' % (control))
        else:
            (status, output) = commands.getstatusoutput(
                'amixer set "%s" mute' % (control))
            if status != 0:
                log.warning('Problem with amixer set "%s" mute' % (control))

    def mute_master(self):
        '''Mutes the Master Control'''
        if self._labels_available and self.activity.hw != XO1:
            self._set_mute(self._master_control, 'Master', True)
        else:
            self.amixer_set('Master', False)

    def unmute_master(self):
        '''Unmutes the Master Control'''
        if self._labels_available and self.activity.hw != XO1:
            self._set_mute(self._master_control, 'Master', True)
        else:
            self.amixer_set('Master', True)

    def set_master(self, master_val):
        '''Sets the Master gain slider settings
        master_val must be given as an integer between 0 and 100 indicating the
        percentage of the slider to be set'''
        if self._labels_available:
            self._set_volume(self._master_control, 'Master', master_val)
        else:
            (status, output) = commands.getstatusoutput(
                'amixer set Master %d%s' % (master_val, '%'))
            if status != 0:
                log.warning('Problem with amixer set Master')

    def get_master(self):
        '''Gets the MIC gain slider settings. The value returned is an
        integer between 0 and 100 and is an indicative of the
        percentage 0 to 100%'''
        if self._labels_available:
            return self._get_volume(self._master_control, 'master')
        else:
            (status, output) = commands.getstatusoutput('amixer get Master')
            if status == 0:
                output = output[find(output, 'Front Left:'):]
                output = output[find(output, '[') + 1:]
                output = output[:find(output, '%]')]
                return int(output)
            else:
                log.warning('amixer: Could not get Master volume')
                return 100

    def set_bias(self, bias_state=False):
        '''Enables / disables bias voltage.'''
        if self._labels_available and self.activity.hw != XO1:
            if self._mic_bias_control is None:
                log.warning('set_bias: no bias control in mixer')
                return
            # If there is a flag property, use set_mute
            if self._mic_bias_control not in self._mixer.list_tracks() or \
               hasattr(self._mic_bias_control.props, 'flags'):
                self._set_mute(
                    self._mic_bias_control, 'Mic Bias', not bias_state)
            # We assume that values are sorted from lowest (=off) to highest.
            # Since they are mixed strings ('Off', '50%', etc.), we cannot
            # easily ensure this by sorting with the default sort order.
            elif bias_state:  # Otherwise, set with volume
                log.debug('setting bias to %s' % (
                        str(self._mic_bias_control.max_volume)))
                self._mixer.set_volume(self._mic_bias_control,
                                       self._mic_bias_control.max_volume)
            else:
                log.debug('setting bias to %s' % (
                        str(self._mic_bias_control.min_volume)))
                self._mixer.set_volume(self._mic_bias_control,
                                       self._mic_bias_control.min_volume)
        elif not self._labels_available:
            self.amixer_set('V_REFOUT Enable', bias_state)
        else:
            self.amixer_set('MIC Bias Enable', bias_state)

    def get_bias(self):
        '''Check whether bias voltage is enabled.'''
        if self._labels_available:
            if self._mic_bias_control is None:
                log.warning('get_bias: no bias control in mixer')
                return False
            if self._mic_bias_control not in self._mixer.list_tracks() or \
               hasattr(self._mic_bias_control.props, 'flags'):
                return not self._get_mute(
                    self._mic_bias_control, 'Mic Bias', False)
            value = self._mixer.get_volume(self._mic_bias_control)
            log.debug('get_bias volume is %s' % (str(value)))
            if value == self._mic_bias_control.min_volume:
                return False
            return True
        else:
            (status, output) = commands.getstatusoutput(
                'amixer get "V_REFOUT Enable"')
            if status == 0:
                output = output[find(output, 'Mono:'):]
                output = output[find(output, '[') + 1:]
                output = output[:find(output, ']')]
                if output == 'on':
                    return True
                return False
            else:
                log.warning('amixer: Could not get mic bias voltage')
                return False

    def set_dc_mode(self, dc_mode=False):
        '''Sets the DC Mode Enable control
        pass False to mute and True to unmute'''
        if self._labels_available and self.activity.hw != XO1:
            if self._dc_control is not None:
                self._set_mute(self._dc_control, 'DC mode', not dc_mode)
        else:
            self.amixer_set('DC Mode Enable', dc_mode)

    def get_dc_mode(self):
        '''Returns the setting of DC Mode Enable control
        i.e. True: Unmuted and False: Muted'''
        if self._labels_available:
            if self._dc_control is not None:
                return not self._get_mute(self._dc_control, 'DC mode', False)
            else:
                return False
        else:
            (status, output) = commands.getstatusoutput(
                'amixer get "DC Mode Enable"')
            if status == 0:
                output = output[find(output, 'Mono:'):]
                output = output[find(output, '[') + 1:]
                output = output[:find(output, ']')]
                if output == 'on':
                    return True
                return False
            else:
                log.warning('amixer: Could not get DC Mode')
                return False

    def set_mic_boost(self, mic_boost=False):
        '''Set Mic Boost.
        True = +20dB, False = 0dB'''
        if self._labels_available:
            if self._mic_boost_control is None:
                log.warning('set_mic_boost: no boost control in mixer')
                return
            # If there is a flag property, use set_mute
            if self._mic_boost_control not in self._mixer.list_tracks() or \
               hasattr(self._mic_boost_control.props, 'flags'):
                self._set_mute(
                    self._mic_boost_control, 'Mic Boost', not mic_boost)
            # Otherwise, set volume to max or min value
            elif mic_boost:
                log.debug('setting boost to %s' % (
                        str(self._mic_boost_control.max_volume)))
                self._mixer.set_volume(self._mic_boost_control,
                                       self._mic_boost_control.max_volume)
            else:
                log.debug('setting boost to %s' % (
                        str(self._mic_boost_control.min_volume)))
                self._mixer.set_volume(self._mic_boost_control,
                                       self._mic_boost_control.min_volume)
        else:
            self.amixer_set('Mic Boost (+20dB)', mic_boost)

    def get_mic_boost(self):
        '''Return Mic Boost setting.
        True = +20dB, False = 0dB'''
        if self._labels_available:
            if self._mic_boost_control is None:
                log.warning('get_mic_boost: no boost control in mixer')
                return False
            if self._mic_boost_control not in self._mixer.list_tracks() or \
               hasattr(self._mic_boost_control.props, 'flags'):
                return not self._get_mute(
                    self._mic_boost_control, 'Mic Boost', False)
            else:  # Compare to min value
                value = self._mixer.get_volume(self._mic_boost_control)
                log.debug('get_mic_boost volume is %s' % (str(value)))
                if value != self._mic_boost_control.min_volume:
                    return True
                return False
        else:
            (status, output) = commands.getstatusoutput(
                'amixer get "Mic Boost (+20dB)"')
            if status == 0:
                output = output[find(output, 'Mono:'):]
                output = output[find(output, '[') + 1:]
                output = output[:find(output, ']')]
                if output == 'on':
                    return True
                return False
            else:
                log.warning('amixer: Could not get mic boost')
                return False

    def set_capture_gain(self, capture_val):
        '''Sets the Capture gain slider settings capture_val must be
        given as an integer between 0 and 100 indicating the
        percentage of the slider to be set'''
        if self._labels_available and self.activity.hw != XO1:
            if self._capture_control is not None:
                self._set_volume(self._capture_control, 'Capture', capture_val)
        else:
            (status, output) = commands.getstatusoutput(
                'amixer set Capture %d%s' % (capture_val, '%'))
            if status != 0:
                log.warning('Problem with amixer set Capture')

    def get_capture_gain(self):
        '''Gets the Capture gain slider settings. The value returned
        is an integer between 0 and 100 and is an indicative of the
        percentage 0 to 100%'''
        if self._labels_available:
            if self._capture_control is not None:
                return self._get_volume(self._capture_control, 'Capture')
            else:
                return 0
        else:
            (status, output) = commands.getstatusoutput('amixer get Capture')
            if status == 0:
                output = output[find(output, 'Front Left:'):]
                output = output[find(output, '[') + 1:]
                output = output[:find(output, '%]')]
                return int(output)
            else:
                log.warning('amixer: Could not get Capture level')
                return 100

    def set_mic_gain(self, mic_val):
        '''Sets the MIC gain slider settings mic_val must be given as
        an integer between 0 and 100 indicating the percentage of the
        slider to be set'''
        if self._labels_available and self.activity.hw != XO1:
            self._set_volume(self._mic_gain_control, 'Mic', mic_val)
        else:
            (status, output) = commands.getstatusoutput(
                'amixer set Mic %d%s' % (mic_val, '%'))
            if status != 0:
                log.warning('Problem with amixer set Mic')

    def get_mic_gain(self):
        '''Gets the MIC gain slider settings. The value returned is an
        integer between 0 and 100 and is an indicative of the
        percentage 0 to 100%'''
        if self._labels_available:
            return self._get_volume(self._mic_gain_control, 'Mic')
        else:
            (status, output) = commands.getstatusoutput('amixer get Mic')
            if status == 0:
                output = output[find(output, 'Mono:'):]
                output = output[find(output, '[') + 1:]
                output = output[:find(output, '%]')]
                return int(output)
            else:
                log.warning('amixer: Could not get mic gain level')
                return 100

    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        '''Set the type of sensor you want to use. Set sensor_type according
        to the following
        SENSOR_AC_NO_BIAS - AC coupling with Bias Off --> Very rarely used.
            Use when connecting a dynamic microphone externally
        SENSOR_AC_BIAS - AC coupling with Bias On --> The default settings.
            The internal MIC uses these
        SENSOR_DC_NO_BIAS - DC coupling with Bias Off --> measuring voltage
            output sensor. For example LM35 which gives output proportional
            to temperature
        SENSOR_DC_BIAS - DC coupling with Bias On --> measuring resistance.
        '''
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (False, False, 50, True),
            SENSOR_AC_BIAS: (False, True, 40, True),
            SENSOR_DC_NO_BIAS: (True, False, 0, False),
            SENSOR_DC_BIAS: (True, True, 0, False)
        }
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        log.debug('Set sensor type to %s' % (str(sensor_type)))
        self._set_sensor_type(mode, bias, gain, boost)

    def _set_sensor_type(self, mode=None, bias=None, gain=None, boost=None):
        '''Helper to modify (some) of the sensor settings.'''

        log.debug('parameters: dc mode: %s, bias: %s, gain: %s, boost: %s' % (
                str(mode), str(bias), str(gain), str(boost)))
        if mode is not None and mode != self.get_dc_mode():
            # If we change to/from dc mode, we need to rebuild the pipelines
            log.debug('dc mode has changed')
            self.stop_grabbing()
            self._unlink_sink_queues()
            self.set_dc_mode(mode)
            log.debug('dcmode is: %s' % (str(self.get_dc_mode())))
            self.start_grabbing()

        if bias is not None:
            self.set_bias(bias)
            if self._mic_bias_control is not None:
                log.debug('bias is: %s' % (str(self.get_bias())))

        if gain is not None:
            self.set_capture_gain(gain)
            if self._capture_control is not None:
                log.debug('gain is %s' % (str(self.get_capture_gain())))

        if boost is not None:
            self.set_mic_boost(boost)
            if self._mic_boost_control is not None:
                log.debug('boost is %s' % (str(self.get_mic_boost())))

        self.save_state()

    def on_activity_quit(self):
        '''When Activity quits'''
        log.debug('Quitting')
        self.set_mic_boost(QUIT_MIC_BOOST)
        self.set_dc_mode(QUIT_DC_MODE_ENABLE)
        self.set_capture_gain(QUIT_CAPTURE_GAIN)
        self.set_bias(QUIT_BIAS)
        self.stop_sound_device()
        if self.logging_state:
            self.activity.data_logger.stop_session()


class AudioGrab_XO1(AudioGrab):
    ''' Use default parameters for OLPC XO 1.0 laptop '''
    pass


class AudioGrab_XO15(AudioGrab):
    ''' Override parameters for OLPC XO 1.5 laptop '''
    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        '''Helper to modify (some) of the sensor settings.'''
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (False, False, 80, True),
            SENSOR_AC_BIAS: (False, True, 80, True),
            SENSOR_DC_NO_BIAS: (True, False, 80, False),
            SENSOR_DC_BIAS: (True, True, 90, False)
        }
        log.debug('Set Sensor Type to %s' % (str(sensor_type)))
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        self._set_sensor_type(mode, bias, gain, boost)


class AudioGrab_XO175(AudioGrab):
    ''' Override parameters for OLPC XO 1.75 laptop '''
    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        '''Helper to modify (some) of the sensor settings.'''
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (False, False, 80, True),
            SENSOR_AC_BIAS: (False, True, 80, True),
            SENSOR_DC_NO_BIAS: (True, False, 80, False),
            SENSOR_DC_BIAS: (True, True, 90, False)
        }
        log.debug('Set Sensor Type to %s' % (str(sensor_type)))
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        self._set_sensor_type(mode, bias, gain, boost)


class AudioGrab_Unknown(AudioGrab):
    ''' Override parameters for generic hardware '''
    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        '''Helper to modify (some) of the sensor settings.'''
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (None, False, 50, True),
            SENSOR_AC_BIAS: (None, True, 40, True),
            SENSOR_DC_NO_BIAS: (True, False, 80, False),
            SENSOR_DC_BIAS: (True, True, 90, False)
        }
        log.debug('Set Sensor Type to %s' % (str(sensor_type)))
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        self._set_sensor_type(mode, bias, gain, boost)
