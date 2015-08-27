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
import subprocess
import traceback
from string import find
from threading import Timer
from numpy import append
from numpy.fft import rfft

from config import RATE, BIAS, DC_MODE_ENABLE, CAPTURE_GAIN, MIC_BOOST,\
                   MAX_LOG_ENTRIES, QUIT_MIC_BOOST, QUIT_DC_MODE_ENABLE,\
                   QUIT_CAPTURE_GAIN, QUIT_BIAS, DISPLAY_DUTY_CYCLE, XO1, \
                   XO15, XO175, XO4, MAX_GRAPHS

import logging

log = logging.getLogger('measure-activity')
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
            activity is the parent class """

        self.callable1 = callable1
        self.activity = activity

        if self.activity.hw == XO1:
            self._voltage_gain = 0.00002225
            self._voltage_bias = 1.140
        elif self.activity.hw == XO15:
            self._voltage_gain = -0.0001471
            self._voltage_bias = 1.695
        elif self.activity.hw in [XO175, XO4]:
            self._voltage_gain = 0.000051
            self._voltage_bias = 1.372
        else:  # XO 3.0
            self._voltage_gain = 0.00007692
            self._voltage_bias = 0.719

        self.rate = RATE
        if self.activity.hw == XO1:
            log.debug('setting channels to 1')
            self.channels = 1
        else:
            log.warning('Guessing there are 2 channels')
            self.channels = 2

        self.we_are_logging = False
        self._log_this_sample = False
        self._logging_timer = None
        self._logging_counter = 0
        self._image_counter = 0
        self._logging_interval = 0
        self._channels_logged = []
        self._busy = False
        self._take_screenshot = True
        self._dont_queue_the_buffer = False
        self._dc_control = None
        self._mic_bias_control = None
        self._capture_control = None
        self._mic_boost_control = None
        self._labels_available = True  # Query controls for device names
        self._display_counter = DISPLAY_DUTY_CYCLE

        self._query_mixer()
        
        self.activity.wave.set_channels(self.channels)
        for i in range(self.channels):
            self._channels_logged.append(False)

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
                                                          'mic1 boost',
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
        if self._pad_count == self.channels:
            log.debug('pipeline added...')
            self.activity.sensor_toolbar.unlock_radio_buttons()

    def set_handoff_signal(self, handoff_state):
        '''Sets whether the handoff signal would generate an interrupt
        or not'''
        for i in range(len(self.fakesink)):
            self.fakesink[i].set_property('signal-handoffs', handoff_state)

    def _new_buffer(self, buf, channel):
        ''' Use a new buffer '''
        if not self._dont_queue_the_buffer:
            self.callable1(buf, channel=channel)

    def on_buffer(self, element, data_buffer, pad, channel):
        '''The function that is called whenever new data is available
        This is the signal handler for the handoff signal'''
        temp_buffer = fromstring(data_buffer, 'int16')
        if not self._dont_queue_the_buffer:
            self._new_buffer(temp_buffer, channel=channel)

        if self._busy:  # busy writing previous sample
            return False
        if self.we_are_logging:
            if self._logging_counter == MAX_LOG_ENTRIES:
                self._logging_counter = 0
                self.we_are_logging = False
                self.activity.data_logger.stop_session()
            else:
                if self._logging_interval == 0:
                    self._emit_for_logging(temp_buffer, channel=channel)
                    self._log_this_sample = False
                    self.we_are_logging = False
                    self.activity.data_logger.stop_session()
                elif self._log_this_sample:
                    # Sample channels in order
                    if self._channels_logged.index(False) == channel:
                        self._channels_logged[channel] = True
                        self._emit_for_logging(temp_buffer, channel=channel)
                        # Have we logged every channel?
                        if self._channels_logged.count(True) == self.channels:
                            self._log_this_sample = False
                            for i in range(self.channels):
                                self._channels_logged[i] = False
                            self._logging_counter += 1

        # In sensor mode, periodly update the textbox with a sample value
        if self.activity.CONTEXT == 'sensor' and not self.we_are_logging:
            # Only update display every nth time, where n=DISPLAY_DUTY_CYCLE
            if self._display_counter == 0:
                if self.activity.sensor_toolbar.mode == 'resistance':
                    self.activity.sensor_toolbar.set_sample_value(
                        int(self._calibrate_resistance(temp_buffer)),
                        channel=channel)
                else:
                    self.activity.sensor_toolbar.set_sample_value(
                        '%0.3f' % (self._calibrate_voltage(temp_buffer)),
                        channel=channel)
                self._display_counter = DISPLAY_DUTY_CYCLE
            else:
                self._display_counter -= 1
        return False

    def _sample_sound(self, data_buffer):
        ''' The average magnitude of the sound '''
        return _avg(data_buffer, abs_value=True)

    def _sample_frequency(self, data_buffer):
        ''' The maximum frequency in the sample '''
        buf = rfft(data_buffer)
        buf = abs(buf)
        maxi = buf.argmax()
        if maxi == 0:
            pitch = 0.0
        else:  # Simple interpolation
            a, b, c = buf[maxi - 1], buf[maxi], buf[maxi + 1]
            maxi -= a / float(a + b + c)
            maxi += c / float(a + b + c)
            pitch = maxi * 48000 / (len(buf) * 2)
        # Convert output to Hertz
        return pitch

    def _calibrate_resistance(self, data_buffer):
        ''' Return calibrated value for resistance '''
        # See <http://bugs.sugarlabs.org/ticket/552#comment:7>
        avg_buffer = _avg(data_buffer)
        if self.activity.hw == XO1:
            return 2.718 ** ((avg_buffer * 0.000045788) + 8.0531)
        elif self.activity.hw == XO15:
            if avg_buffer > 0:
                return (420000000 / avg_buffer) - 13500
            else:
                return 420000000
        elif self.activity.hw in [XO175, XO4]:
            return (180000000 / (30700 - avg_buffer)) - 3150
        else:  # XO 3.0
            return (46000000 / (30514 - avg_buffer)) - 1150

    def _calibrate_voltage(self, data_buffer):
        ''' Return calibrated value for voltage '''
        # See <http://bugs.sugarlabs.org/ticket/552#comment:7>
        return _avg(data_buffer) * self._voltage_gain + self._voltage_bias

    def set_freeze_the_display(self, freeze=False):
        ''' Useful when just the display is needed to be frozen, but
        logging should continue '''
        self._dont_queue_the_buffer = not freeze

    def take_screenshot(self):
        ''' Capture the current screen to the Journal '''
        log.debug('taking a screenshot %d' % (self._logging_counter))
        self.set_logging_params(start_stop=True, interval=0, screenshot=True)

    def get_freeze_the_display(self):
        '''Returns state of queueing the buffer'''
        return not self._dont_queue_the_buffer

    def _emit_for_logging(self, data_buffer, channel=0):
        '''Sends the data for logging'''
        if not self._busy:
            self._busy = True
            if self._take_screenshot:
                if self.activity.data_logger.take_screenshot(
                    self._image_counter):
                    self._image_counter += 1
                else:
                    log.debug('failed to take screenshot %d' % (
                            self._logging_counter))
                self._busy = False
                return
            if self.activity.CONTEXT == 'sensor':
                if self.activity.sensor_toolbar.mode == 'resistance':
                    value = self._calibrate_resistance(data_buffer)
                    value_string = int(value)
                else:
                    value = self._calibrate_voltage(data_buffer)
                    value_string = '0.3f' % (value)
            else:
                if not self.activity.wave.get_fft_mode():
                    value = self._sample_sound(data_buffer)
                else:
                    value = self._sample_frequency(data_buffer)
                value_string = int(value)
            self.activity.sensor_toolbar.set_sample_value(
                value_string, channel=channel)
            if self.channels > 1:
                self.activity.data_logger.write_value(
                    value_string, channel=channel,
                    sample=self._logging_counter)
            else:
                self.activity.data_logger.write_value(
                    value_string, sample=self._logging_counter)
            self._busy = False
        else:
            log.debug('skipping sample %d.%d' % (
                    self._logging_counter, channel))

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
        ''' Configures for logging of data: starts or stops a session;
        sets the logging interval; and flags if screenshot is taken. '''
        self.we_are_logging = start_stop
        self._logging_interval = interval
        if not start_stop:
            if self._logging_timer:
                self._logging_timer.cancel()
                self._logging_timer = None
                self._log_this_sample = False
                self._logging_counter = 0
        elif interval != 0:
            self._make_timer()
        self._take_screenshot = screenshot
        self._busy = False

    def _sample_now(self):
        ''' Log the current sample now. This method is called from the
        _logging_timer object when the interval expires. '''
        self._log_this_sample = True
        self._make_timer()

    def _make_timer(self):
        ''' Create the next timer that will trigger data logging. '''
        self._logging_timer = Timer(self._logging_interval, self._sample_now)
        self._logging_timer.start()

    def set_sampling_rate(self, sr):
        ''' Sets the sampling rate of the logging device. Sampling
        rate must be given as an integer for example 16000 for setting
        16Khz sampling rate The sampling rate would be set in the
        device to the nearest available. '''
        self.pause_grabbing()
        caps_str = 'audio/x-raw-int,rate=%d,channels=%d,depth=16' % (
            sr, self.channels)
        self.caps1.set_property('caps', gst.caps_from_string(caps_str))
        self.resume_grabbing()

    def get_sampling_rate(self):
        ''' Gets the sampling rate of the capture device '''
        return int(self.caps1.get_property('caps')[0]['rate'])

    def start_grabbing(self):
        '''Called right at the start of the Activity'''
        self.start_sound_device()
        self.set_handoff_signal(True)

    def pause_grabbing(self):
        '''When Activity goes into background'''
        if self.we_are_logging:
            log.debug('We are logging... will not pause grabbing.')
        else:
            log.debug('Pause grabbing.')
            self.save_state()
            self.stop_sound_device()
        return

    def resume_grabbing(self):
        '''When Activity becomes active after going to background'''
        if self.we_are_logging:
            log.debug('We are logging... already grabbing.')
        else:
            log.debug('Restore grabbing.')
            self.restore_state()
            self.start_sound_device()
            self.set_handoff_signal(True)
        return

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

    def restore_state(self):
        '''Put back all audio control settings from the saved state'''
        log.debug('Restore state')
        self.set_master(self.master)
        self.set_bias(self.bias)
        self.stop_grabbing()
        if self.channels > 1:
            self._unlink_sink_queues()
        self.set_dc_mode(self.dc_mode)
        self.start_grabbing()
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
            output = check_output(
                ['amixer', 'set', "%s" % (control), 'unmute'],
                'Problem with amixer set "%s" unmute' % (control))
        else:
            output = check_output(
                ['amixer', 'set', "%s" % (control), 'mute'],
                'Problem with amixer set "%s" mute' % (control))

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
            output = check_output(
                ['amixer', 'set', 'Master', "%d%s" % (master_val, '%')],
                'Problem with amixer set Master')

    def get_master(self):
        '''Gets the MIC gain slider settings. The value returned is an
        integer between 0 and 100 and is an indicative of the
        percentage 0 to 100%'''
        if self._labels_available:
            return self._get_volume(self._master_control, 'master')
        else:
            output = check_output(['amixer', 'get', 'Master'],
                                  'amixer: Could not get Master volume')
            if output is None:
                return 100
            else:
                output = output[find(output, 'Front Left:'):]
                output = output[find(output, '[') + 1:]
                output = output[:find(output, '%]')]
                return int(output)

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
            output = check_output(['amixer', 'get', "V_REFOUT Enable"],
                                  'amixer: Could not get mic bias voltage')
            if output is None:
                return False
            else:
                output = output[find(output, 'Mono:'):]
                output = output[find(output, '[') + 1:]
                output = output[:find(output, ']')]
                if output == 'on':
                    return True
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
            output = check_output(['amixer', 'get', "DC Mode Enable"],
                                  'amixer: Could not get DC Mode')
            if output is None:
                return False
            else:
                output = output[find(output, 'Mono:'):]
                output = output[find(output, '[') + 1:]
                output = output[:find(output, ']')]
                if output == 'on':
                    return True
                return False

    def set_mic_boost(self, mic_boost=False):
        '''Set Mic Boost.
        for analog mic boost: True = +20dB, False = 0dB
        for mic1 boost: True = 8, False = 0'''
        if self._labels_available:
            if self._mic_boost_control is None:
                log.warning('set_mic_boost: no boost control in mixer')
                return
            # If there is a volume, use set volume
            if hasattr(self._mic_boost_control, 'min_volume'):
                if mic_boost:
                    log.debug('setting boost to %s' % (
                            str(self._mic_boost_control.max_volume)))
                    self._set_volume(self._mic_boost_control, 'boost', 100)
                else:
                    log.debug('setting boost to %s' % (
                            str(self._mic_boost_control.min_volume)))
                    self._set_volume(self._mic_boost_control, 'boost', 0)
            # Else if there is a flag property, use set_mute
            elif self._mic_boost_control not in self._mixer.list_tracks() or \
               hasattr(self._mic_boost_control.props, 'flags'):
                log.debug('setting boost to %s' % (str(not mic_boost)))
                self._set_mute(
                    self._mic_boost_control, 'Mic Boost', not mic_boost)
        else:
            self.amixer_set('Mic Boost (+20dB)', mic_boost)

    def get_mic_boost(self):
        '''Return Mic Boost setting.
        for analog mic boost: True = +20dB, False = 0dB
        for mic1 boost: True = 8, False = 0'''
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
            output = check_output(['amixer', 'get', "Mic Boost (+20dB)"],
                                  'amixer: Could not get mic boost')
            if output is None:
                return False
            else:
                output = output[find(output, 'Mono:'):]
                output = output[find(output, '[') + 1:]
                output = output[:find(output, ']')]
                if output == 'on':
                    return True
                return False

    def set_capture_gain(self, capture_val):
        '''Sets the Capture gain slider settings capture_val must be
        given as an integer between 0 and 100 indicating the
        percentage of the slider to be set'''
        if self._labels_available and self.activity.hw != XO1:
            if self._capture_control is not None:
                self._set_volume(self._capture_control, 'Capture', capture_val)
        else:
            output = check_output(
                ['amixer', 'set', 'Capture', "%d%s" % (capture_val, '%')],
                'Problem with amixer set Capture')

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
            output = check_output(['amixer', 'get', 'Capture'],
                                  'amixer: Could not get Capture level')
            if output is None:
                return 100
            else:
                output = output[find(output, 'Front Left:'):]
                output = output[find(output, '[') + 1:]
                output = output[:find(output, '%]')]
                return int(output)

    def set_mic_gain(self, mic_val):
        '''Sets the MIC gain slider settings mic_val must be given as
        an integer between 0 and 100 indicating the percentage of the
        slider to be set'''
        if self._labels_available and self.activity.hw != XO1:
            self._set_volume(self._mic_gain_control, 'Mic', mic_val)
        else:
            output = check_output(
                ['amixer', 'set', 'Mic', "%d%s" % (mic_val, '%')],
                'Problem with amixer set Mic')

    def get_mic_gain(self):
        '''Gets the MIC gain slider settings. The value returned is an
        integer between 0 and 100 and is an indicative of the
        percentage 0 to 100%'''
        if self._labels_available:
            return self._get_volume(self._mic_gain_control, 'Mic')
        else:
            output = check_output(['amixer', 'get', 'Mic'],
                                  'amixer: Could not get mic gain level')
            if output is None:
                return 100
            else:
                output = output[find(output, 'Mono:'):]
                output = output[find(output, '[') + 1:]
                output = output[:find(output, '%]')]
                return int(output)

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

        if mode is not None:
            # If we change to/from dc mode, we need to rebuild the pipelines
            log.debug('sensor mode has changed')
            self.stop_grabbing()
            if self.channels > 1:
                self._unlink_sink_queues()
            self.start_grabbing()
            self.set_dc_mode(mode)
            log.debug('dcmode is: %s' % (str(self.get_dc_mode())))
            if self.activity.hw == 'XO1' and \
               hasattr(self.activity, 'sensor_toolbar'):
                self.activity.sensor_toolbar.unlock_radio_buttons()

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
        if self.we_are_logging:
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

    def on_activity_quit(self):
        AudioGrab.on_activity_quit(self)
        output = check_output(
            ['amixer', 'set', 'MIC1 Boost', "87%"],
            'restore MIC1 Boost')  # OLPC OS up to 13.2.5
        output = check_output(
            ['amixer', 'set', 'Analog Mic Boost', "62%"],
            'restore Analog Mic Boost')  # OLPC OS after 13.2.5


class AudioGrab_XO4(AudioGrab):
    ''' Override parameters for OLPC XO 4 laptop '''
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

    def on_activity_quit(self):
        AudioGrab.on_activity_quit(self)
        output = check_output(
            ['amixer', 'set', 'Analog Mic Boost', "62%"],
            'restore Analog Mic Boost')


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


def check_output(command, warning):
    ''' Workaround for old systems without subprocess.check_output'''
    if hasattr(subprocess, 'check_output'):
        try:
            output = subprocess.check_output(command)
        except subprocess.CalledProcessError:
            log.warning(warning)
            return None
    else:
        import commands

        cmd = ''
        for c in command:
            cmd += c
            cmd += ' '
        (status, output) = commands.getstatusoutput(cmd)
        if status != 0:
            log.warning(warning)
            return None
    return output
