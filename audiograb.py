#! /usr/bin/python3
#
# Author:  Arjun Sarwal   arjun@laptop.org
# Copyright (C) 2007, Arjun Sarwal
# Copyright (C) 2009-11 Walter Bender
# Copyright (C) 2009, Benjamin Berg, Sebastian Berg
# Copyright (C) 2009, Sayamindu Dasgupta
# Copyright (C) 2010, Sascha Silbe
# Copyright (C) 2016, James Cameron [GStreamer 1.0]
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA


from numpy import fromstring
import subprocess
import traceback

from threading import Timer
from numpy.fft import rfft

from config import RATE, BIAS, DC_MODE_ENABLE, CAPTURE_GAIN, MIC_BOOST, \
    MAX_LOG_ENTRIES, QUIT_MIC_BOOST, QUIT_DC_MODE_ENABLE, QUIT_CAPTURE_GAIN, \
    QUIT_BIAS, DISPLAY_DUTY_CYCLE, XO1, XO15, XO175, XO4, MAX_GRAPHS

import logging

from gi.repository import Gst

log = logging.getLogger('measure-activity')
log.setLevel(logging.DEBUG)


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
            self.channels = 1
        else:
            self.channels = 2

        self.we_are_logging = False
        self._log_this_sample = False
        self._logging_timer = None
        self._logging_counter = 0
        self._image_counter = 0
        self._logging_interval = 0
        self._channels_logged = []
        self._busy = False

        self._dont_queue_the_buffer = False

        self._display_counter = DISPLAY_DUTY_CYCLE

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
        self.pipeline = Gst.Pipeline.new('pipeline')
        self.alsasrc = Gst.ElementFactory.make('alsasrc', 'alsa-source')
        self.pipeline.add(self.alsasrc)
        self.caps1 = Gst.ElementFactory.make('capsfilter', 'caps1')
        self.pipeline.add(self.caps1)
        caps_str = 'audio/x-raw,rate=(int)%d,channels=(int)%d,depth=(int)16' \
            % (RATE, self.channels)
        self.caps1.props.caps = Gst.caps_from_string(caps_str)
        if self.channels == 1:
            self.fakesink.append(Gst.ElementFactory.make('fakesink', 'fsink'))
            self.pipeline.add(self.fakesink[0])
            self.fakesink[0].connect('handoff', self.on_buffer, 0)
            self.fakesink[0].props.signal_handoffs = True
            self.alsasrc.link(self.caps1)
            self.caps1.link(self.fakesink[0])
        else:
            if not hasattr(self, 'splitter'):
                self.splitter = Gst.ElementFactory.make('deinterleave', None)
                self.pipeline.add(self.splitter)
                self.splitter.props.keep_positions = True
                self.splitter.connect('pad-added', self._splitter_pad_added)
                self.alsasrc.link(self.caps1)
                self.caps1.link(self.splitter)

            for i in range(self.channels):
                self.queue.append(Gst.ElementFactory.make('queue', None))
                self.pipeline.add(self.queue[i])
                self.fakesink.append(Gst.ElementFactory.make('fakesink', None))
                self.pipeline.add(self.fakesink[i])
                self.fakesink[i].connect('handoff', self.on_buffer, i)
                self.fakesink[i].props.signal_handoffs = True

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
        self.pads.append(pad)
        if (self._pad_count < min(self.channels, MAX_GRAPHS)):
            pad.link(self.queue[self._pad_count].get_static_pad('sink'))
            self.queue[self._pad_count].get_static_pad('src').link(
                self.fakesink[self._pad_count].get_static_pad('sink'))
            self._pad_count += 1
        else:
            log.debug('ignoring channels > %d' % (min(self.channels,
                                                      MAX_GRAPHS)))
        if self._pad_count == self.channels:
            self.activity.sensor_toolbar.unlock_radio_buttons()

    def set_handoff_signal(self, handoff_state):
        '''Sets whether the handoff signal would generate an interrupt
        or not'''
        for i in range(len(self.fakesink)):
            self.fakesink[i].signal_handoffs = handoff_state

    def _new_buffer(self, buf, channel):
        ''' Use a new buffer '''
        if not self._dont_queue_the_buffer:
            self.callable1(buf, channel=channel)

    def on_buffer(self, element, data_buffer, pad, channel):
        '''The function that is called whenever new data is available
        This is the signal handler for the handoff signal'''
        size = data_buffer.get_size()
        temp_buffer = fromstring(data_buffer.extract_dup(0, size), 'int16')
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

    def get_freeze_the_display(self):
        '''Returns state of queueing the buffer'''
        return not self._dont_queue_the_buffer

    def _emit_for_logging(self, data_buffer, channel=0):
        '''Sends the data for logging'''
        if not self._busy:
            self._busy = True
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
        Gst.Event.new_flush_start()
        self.pipeline.set_state(Gst.State.PLAYING)

    def stop_sound_device(self):
        '''Stop grabbing data from capture device'''
        Gst.Event.new_flush_stop(False)
        self.pipeline.set_state(Gst.State.NULL)

    def set_logging_params(self, start_stop=False, interval=0):
        ''' Configures for logging of data: starts or stops a session;
        and sets the logging interval. '''
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
        self.caps1.props.caps = Gst.caps_from_string(caps_str)
        self.resume_grabbing()

    def get_sampling_rate(self):
        ''' Gets the sampling rate of the capture device '''
        _, value = self.caps1.props.caps.get_structure(0).get_int('rate')
        return int(value)

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

    def save_state(self):
        '''Saves the state of all audio controls'''
        self.master = self.get_master()
        self.bias = self.get_bias()
        self.dc_mode = self.get_dc_mode()
        self.capture_gain = self.get_capture_gain()
        self.mic_boost = self.get_mic_boost()

    def restore_state(self):
        '''Put back all audio control settings from the saved state'''
        self.set_master(self.master)
        self.set_bias(self.bias)
        self.stop_grabbing()
        if self.channels > 1:
            self._unlink_sink_queues()
        self.set_dc_mode(self.dc_mode)
        self.start_grabbing()
        self.set_capture_gain(self.capture_gain)
        self.set_mic_boost(self.mic_boost)

    def amixer_set(self, control, state):
        ''' Direct call to amixer for old systems. '''
        if state:
            check_output(
                ['amixer', 'set', "%s" % (control), 'unmute'],
                'Problem with amixer set "%s" unmute' % (control))
        else:
            check_output(
                ['amixer', 'set', "%s" % (control), 'mute'],
                'Problem with amixer set "%s" mute' % (control))

    def mute_master(self):
        '''Mutes the Master Control'''
        self.amixer_set('Master', False)

    def unmute_master(self):
        '''Unmutes the Master Control'''
        self.amixer_set('Master', True)

    def set_master(self, master_val):
        '''Sets the Master gain slider settings
        master_val must be given as an integer between 0 and 100 indicating the
        percentage of the slider to be set'''
        check_output(
            ['amixer', 'set', 'Master', "%d%s" % (master_val, '%')],
            'Problem with amixer set Master')

    def get_master(self):
        '''Gets the MIC gain slider settings. The value returned is an
        integer between 0 and 100 and is an indicative of the
        percentage 0 to 100%'''
        output = check_output(['amixer', 'get', 'Master'],
        
                              'amixer: Could not get Master volume')
        if output is None:
            return 100
        else:
            pos = output.find('Front Left:')
            if pos == -1:
                pos = output.find('Mono:')
            output = output[pos:]
            output = output[output.find('[') + 1:]
            output = output[:output.find('%]')]
            return int(output)

    def set_bias(self, bias_state=False):
        '''Enables / disables bias voltage.'''
        if self.activity.hw == XO1:
            self.amixer_set('MIC Bias Enable', bias_state)
        else:
            self.amixer_set('V_REFOUT Enable', bias_state)

    def get_bias(self):
        '''Check whether bias voltage is enabled.'''
        if self.activity.hw == XO1:
            control = 'MIC Bias Enable'
        else:
            control = 'V_REFOUT Enable'
        output = check_output(['amixer', 'get', control],
                              'amixer: Could not get mic bias voltage')
        if output is None:
            return False
        else:
            output = output[output.find('Mono:'):]
            output = output[output.find('[') + 1:]
            output = output[:output.find(']')]
            if output == 'on':
                return True
            return False

    def set_dc_mode(self, dc_mode=False):
        '''Sets the DC Mode Enable control
        pass False to mute and True to unmute'''
        self.amixer_set('DC Mode Enable', dc_mode)

    def get_dc_mode(self):
        '''Returns the setting of DC Mode Enable control
        i.e. True: Unmuted and False: Muted'''
        output = check_output(['amixer', 'get', "DC Mode Enable"],
                              'amixer: Could not get DC Mode')
        if output is None:
            return False
        else:
            output = output[output.find('Mono:'):]
            output = output[output.find('[') + 1:]
            output = output[:output.find(']')]
            if output == 'on':
                return True
            return False

    def set_mic_boost(self, mic_boost=False):
        '''Set Mic Boost.
        for analog mic boost: True = +20dB, False = 0dB
        for mic1 boost: True = 8, False = 0'''
        self.amixer_set('Mic Boost (+20dB)', mic_boost)

    def get_mic_boost(self):
        '''Return Mic Boost setting.
        for analog mic boost: True = +20dB, False = 0dB
        for mic1 boost: True = 8, False = 0'''
        output = check_output(['amixer', 'get', "Mic Boost (+20dB)"],
                              'amixer: Could not get mic boost')
        if output is None:
            return False
        else:
            output = output[output.find('Mono:'):]
            output = output[output.find('[') + 1:]
            output = output[:output.find(']')]
            if output == 'on':
                return True
            return False

    def set_capture_gain(self, capture_val):
        '''Sets the Capture gain slider settings capture_val must be
        given as an integer between 0 and 100 indicating the
        percentage of the slider to be set'''
        check_output(
            ['amixer', 'set', 'Capture', "%d%s" % (capture_val, '%')],
            'Problem with amixer set Capture')

    def get_capture_gain(self):
        '''Gets the Capture gain slider settings. The value returned
        is an integer between 0 and 100 and is an indicative of the
        percentage 0 to 100%'''
        output = check_output(['amixer', 'get', 'Capture'],
                              'amixer: Could not get Capture level')
        if output is None:
            return 100
        else:
            pos = output.find('Front Left:')
            if pos == -1:
                pos = output.find('Mono:')
            output = output[pos:]
            output = output[output.find('[') + 1:]
            output = output[:output.find('%]')]
            return int(output)

    def set_mic_gain(self, mic_val):
        '''Sets the MIC gain slider settings mic_val must be given as
        an integer between 0 and 100 indicating the percentage of the
        slider to be set'''
        check_output(
            ['amixer', 'set', 'Mic', "%d%s" % (mic_val, '%')],
            'Problem with amixer set Mic')

    def get_mic_gain(self):
        '''Gets the MIC gain slider settings. The value returned is an
        integer between 0 and 100 and is an indicative of the
        percentage 0 to 100%'''
        output = check_output(['amixer', 'get', 'Mic'],
                              'amixer: Could not get mic gain level')
        if output is None:
            return 100
        else:
            output = output[output.find('Mono:'):]
            output = output[output.find('[') + 1:]
            output = output[:output.find('%]')]
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
        self._set_sensor_type(mode, bias, gain, boost)

    def _set_sensor_type(self, mode=None, bias=None, gain=None, boost=None):
        '''Helper to modify (some) of the sensor settings.'''

        if mode is not None:
            # If we change to/from dc mode, we need to rebuild the pipelines
            log.debug('sensor mode has changed')
            self.stop_grabbing()
            if self.channels > 1:
                self._unlink_sink_queues()
            self.start_grabbing()
            self.set_dc_mode(mode)
            log.debug('dcmode is: %s' % (str(self.get_dc_mode())))
            if self.activity.hw == XO1 and \
               hasattr(self.activity, 'sensor_toolbar'):
                self.activity.sensor_toolbar.unlock_radio_buttons()

        if bias is not None:
            self.set_bias(bias)

        if gain is not None:
            self.set_capture_gain(gain)

        if boost is not None:
            self.set_mic_boost(boost)

        self.save_state()

    def on_activity_quit(self):
        '''When Activity quits'''
        self.set_mic_boost(QUIT_MIC_BOOST)
        self.set_dc_mode(QUIT_DC_MODE_ENABLE)
        self.set_capture_gain(QUIT_CAPTURE_GAIN)
        self.set_bias(QUIT_BIAS)
        self.stop_sound_device()
        if self.we_are_logging:
            self.activity.data_logger.stop_session()


class AudioGrab_XO1(AudioGrab):
    ''' Use default parameters for OLPC XO-1 laptop '''
    pass


class AudioGrab_XO15(AudioGrab):
    ''' Override parameters for OLPC XO-1.5 laptop '''
    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        '''Helper to modify (some) of the sensor settings.'''
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (False, False, 80, True),
            SENSOR_AC_BIAS: (False, True, 80, True),
            SENSOR_DC_NO_BIAS: (True, False, 80, False),
            SENSOR_DC_BIAS: (True, True, 90, False)
        }
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        self._set_sensor_type(mode, bias, gain, boost)


class AudioGrab_XO175(AudioGrab):
    ''' Override parameters for OLPC XO-1.75 laptop '''
    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        '''Helper to modify (some) of the sensor settings.'''
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (False, False, 80, True),
            SENSOR_AC_BIAS: (False, True, 80, True),
            SENSOR_DC_NO_BIAS: (True, False, 80, False),
            SENSOR_DC_BIAS: (True, True, 90, False)
        }
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        self._set_sensor_type(mode, bias, gain, boost)

    def on_activity_quit(self):
        AudioGrab.on_activity_quit(self)
        check_output(
            ['amixer', 'set', 'MIC1 Boost', "87%"],
            'restore MIC1 Boost')  # OLPC OS up to 13.2.5
        check_output(
            ['amixer', 'set', 'Analog Mic Boost', "62%"],
            'restore Analog Mic Boost')  # OLPC OS after 13.2.5


class AudioGrab_XO4(AudioGrab):
    ''' Override parameters for OLPC XO-4 laptop '''
    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        '''Helper to modify (some) of the sensor settings.'''
        PARAMETERS = {
            SENSOR_AC_NO_BIAS: (False, False, 80, True),
            SENSOR_AC_BIAS: (False, True, 80, True),
            SENSOR_DC_NO_BIAS: (True, False, 80, False),
            SENSOR_DC_BIAS: (True, True, 90, False)
        }
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        self._set_sensor_type(mode, bias, gain, boost)

    def on_activity_quit(self):
        AudioGrab.on_activity_quit(self)
        check_output(
            ['amixer', 'set', 'Analog Mic Boost', "62%"],
            'restore Analog Mic Boost')


class AudioGrabNoDC(AudioGrab):
    def set_bias(self, bias_state):
        pass

    def get_bias(self):
        return False

    def set_dc_mode(self, dc_mode):
        pass

    def get_dc_mode(self):
        return False

    def get_mic_boost(self):
        return False

    def set_mic_boost(self, value):
        pass


class AudioGrab_NL3(AudioGrabNoDC):
    ''' Override parameters for OLPC NL3 laptop '''
    def set_sensor_type(self, sensor_type=SENSOR_AC_BIAS):
        '''Helper to modify (some) of the sensor settings.'''
        PARAMETERS = {
            SENSOR_AC_BIAS: (None, True, 80, True),
        }
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
        mode, bias, gain, boost = PARAMETERS[sensor_type]
        self._set_sensor_type(mode, bias, gain, boost)


def check_output(command, warning):
    ''' Workaround for old systems without subprocess.check_output'''
    import subprocess
    if hasattr(subprocess, 'check_output'):
        try:
            output = subprocess.check_output(command)
        except subprocess.CalledProcessError:
            log.warning(warning)
            return None
    else:
        import subprocess

        cmd = ''
        for c in command:
            cmd += c
            cmd += ' '
        (status, output) = subprocess.getstatusoutput(cmd)
        if status != 0:
            log.warning(warning)
            return None

    output = output.decode('utf-8')
    return output

