# -*- coding: utf-8 -*-
#! /usr/bin/python
#
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

import gtk
import gobject
from gettext import gettext as _

from config import ICONS_DIR, CAPTURE_GAIN, MIC_BOOST

# Initialize logging.
import logging
log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)
logging.basicConfig()

from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.combobox import ComboBox
from sugar.graphics.toolcombobox import ToolComboBox

# Initialize logging.
import logging
log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)
logging.basicConfig()


class SoundToolbar(gtk.Toolbar):
    """ Set up the toolbar for audio (analog) capture mode """

    SAMPLE_NOW = _('Capture now')
    SAMPLE_30_SEC = _('Every 30 sec.')
    SAMPLE_2_MIN = _('Every 2 min.')
    SAMPLE_10_MIN = _('Every 10 min.')
    SAMPLE_30_MIN = _('Every 30 min.')

    LOWER = 0.0
    UPPER = 1.0

    def __init__(self, activity):
        """ Initialize the toolbar controls. """
        gtk.Toolbar.__init__(self)

        self.activity = activity

        self._STR_BASIC = _('Sound') + ' '
        self._STR1 = _('Time Base') + ' '
        self._STR2 = _('Frequency Base') + ' '
        self._STR3 = ' ' + _('Invert') + ' '
        self._STR_SCALEX = ""
        self._STR_XAXIS_TEXT = \
            _('X Axis Scale: 1 division = %(division)s %(unit)s')
        # TRANSLATORS: This is milli seconds.
        self._ms = _('ms')
        # TRANSLATORS: This is Hertz, so 1/second.
        self._Hz = _('Hz')

        self._update_page_size_id = None

        self.string_for_textbox = ""

        self.gain = 1.0
        self.y_mag = 3.0
        self.capture_gain = CAPTURE_GAIN
        self.mic_boost = MIC_BOOST

        # self.logging_status = False
        self._record = None

        # Set up Time-domain Button
        self.time = ToolButton('domain-time2')
        self.insert(self.time, -1)
        self.time.set_tooltip(_('Time Base'))
        self.time.connect('clicked', self._timefreq_control_cb, True)

        # Set up Frequency-domain Button
        self.freq = ToolButton('domain-freq')
        self.insert(self.freq, -1)
        self.freq.show()
        self.freq.set_tooltip(_('Frequency Base'))
        self.freq.connect('clicked', self._timefreq_control_cb, False)

        # Set up Frequency-control Slider and corresponding buttons
        if not self.activity.has_toolbarbox:
            self.add_frequency_slider(self)

        # Set up the Pause Button
        self._pause = ToolButton('media-playback-pause')
        self.insert(self._pause, -1)
        self._pause.set_tooltip(_('Freeze the display'))
        self._pause.connect('clicked', self._pauseplay_control_cb)

        if self.activity.has_toolbarbox:
            separator = gtk.SeparatorToolItem()
            separator.props.draw = True
            self.insert(separator, -1)
            separator.show()

        self.loginterval_img = gtk.Image()
        self.loginterval_img.set_from_file(ICONS_DIR + 'sample_rate.svg')
        self.loginterval_img_tool = gtk.ToolItem()
        self.loginterval_img_tool.add(self.loginterval_img)
        self.insert(self.loginterval_img_tool, -1)
        
        # Set up the Logging-interval Combo box
        self._loginterval_combo = ComboBox()
        self.interval = [_(self.SAMPLE_NOW),
                         _(self.SAMPLE_30_SEC), 
                         _(self.SAMPLE_2_MIN), 
                         _(self.SAMPLE_10_MIN), 
                         _(self.SAMPLE_30_MIN)]

        if hasattr(self._loginterval_combo, 'set_tooltip_text'):
            self._loginterval_combo.set_tooltip_text(_('Sampling interval'))
        
        self._interval_changed_id = self._loginterval_combo.connect('changed',
                                         self.loginterval_control)

        for i, s in enumerate(self.interval):
            self._loginterval_combo.append_item(i, s, None)
            if s == self.SAMPLE_NOW:
                self._loginterval_combo.set_active(i)

        self._loginterval_tool = ToolComboBox(self._loginterval_combo)
        self.insert(self._loginterval_tool, -1)
        self.logginginterval_status = 'picture'

        # Set up Start/Stop Logging Button
        self._record = ToolButton('media-record')
        self.insert(self._record, -1)
        self._record.set_tooltip(_('Capture sample now'))

        self._record.connect('clicked', self.record_control)

        if self.activity.has_toolbarbox:
            separator = gtk.SeparatorToolItem()
            separator.props.draw = True
            self.insert(separator, -1)

        # Set up Trigger Combo box
        self._trigger_combo = ComboBox()
        self.trigger = [_('None'), _('Rising Edge'), _('Falling Edge')]
        self.trigger_conf = [self.activity.wave.TRIGGER_NONE,
                             self.activity.wave.TRIGGER_POS,
            self.activity.wave.TRIGGER_NEG]

        self._trigger_changed_id = self._trigger_combo.connect('changed',
                                       self.update_trigger_control)

        for i, s in enumerate(self.trigger):
            self._trigger_combo.append_item(i, s, None)
        self._trigger_combo.set_active(0)

        if hasattr(self._trigger_combo, 'set_tooltip_text'):
            self._trigger_combo.set_tooltip_text(_('Create a trigger'))

        self._trigger_tool = ToolComboBox(self._trigger_combo)
        self.insert(self._trigger_tool, -1)
        self.show_all()

        return

    def add_frequency_slider(self, toolbar):
        """ Either on the Sound toolbar or the Main toolbar """
        self._freq_stepper_up = ToolButton('freq-high')
        self._freq_stepper_up.set_tooltip(_('Zoom out'))
        self._freq_stepper_up.connect('clicked', self._freq_stepper_up_cb)

        self.activity.adjustmentf = gtk.Adjustment(0.5, self.LOWER, self.UPPER,
                                                   0.01, 0.1, 0)
        self.activity.adjustmentf.connect('value_changed', self.cb_page_sizef)
        self._freq_range = gtk.HScale(self.activity.adjustmentf)
        self._freq_range.set_inverted(True)
        self._freq_range.set_draw_value(False)
        self._freq_range.set_update_policy(gtk.UPDATE_CONTINUOUS)
        self._freq_range.set_size_request(120, 15)

        self._freq_stepper_down = ToolButton('freq-low')
        self._freq_stepper_down.set_tooltip(_('Zoom in'))
        self._freq_stepper_down.connect('clicked', self._freq_stepper_down_cb)

        self._freq_range_tool = gtk.ToolItem()
        self._freq_range_tool.add(self._freq_range)

        toolbar.insert(self._freq_stepper_up, -1)
        toolbar.insert(self._freq_range_tool, -1)
        toolbar.insert(self._freq_stepper_down, -1)

        return

    def _set_icon_ready(self):
        self._record.set_icon('media-record')
        self._record.show()
        return False

    def _set_icon_stop(self):
        self._record.set_icon('record-stop')
        self._record.show()
        return False

    def record_control_delayed(self, data=None):
        """Depending upon the selected interval, either starts/stops
        a logging session, or just logs the current buffer"""
        if not self.activity.LOGGING_IN_SESSION:
            Xscale = (1.00 / self.activity.audiograb.get_sampling_rate())
            Yscale = 0.0
            interval = self.interval_convert()
            username = self.activity.nick
            self.activity.ji.start_new_session(username, Xscale, Yscale,
                                      self.logginginterval_status)
            self.activity.audiograb.set_logging_params(True, interval, True)
            self.activity.LOGGING_IN_SESSION = True
            self._set_icon_stop()
            if interval == 0:
                # Flash the stop button when grabbing just one image
                gobject.timeout_add(250, self._set_icon_ready)
                self.record_state = False
                self.activity.LOGGING_IN_SESSION = False
                self.logging_status = False
        else:
            self.activity.audiograb.set_logging_params(False)
            self.activity.LOGGING_IN_SESSION = False
            self._set_icon_ready()
        self._set_record_button_tooltip()
        return False

    def record_control(self, data=None):
        self._record.palette.popdown()
        gtk.gdk.flush()
        gobject.timeout_add(10, self.record_control_delayed, data)

    def interval_convert(self):
        """Converts picture/time interval to an integer that denotes the number
        of times the audiograb buffer must be called before a value is written.
        When set to 0, the whole of current buffer will be written
        1second= about 66 ticks at 48khz sampling"""
        if self.logginginterval_status == 'picture':
            return 0
        elif self.logginginterval_status == '30second':
            return 30  #2667
        elif self.logginginterval_status == '2minute':
            return 120  #10668
        elif self.logginginterval_status == '10minute':
            return 600  #53340
        elif self.logginginterval_status == '30minute':
            return 1800  #160000

    def loginterval_control(self, combobox):
        """ The combo box has changed. Set the logging interval
        status correctly and then set the tooltip on the record
        button properly depending upon whether logging is currently
        in progress or not. """
        if (self._loginterval_combo.get_active() != -1):
            if (self._loginterval_combo.get_active() == 0):
                self.logginginterval_status = 'picture'
            elif (self._loginterval_combo.get_active() == 1):
                self.logginginterval_status = '30second'
            elif (self._loginterval_combo.get_active() == 2):
                self.logginginterval_status = '2minute'
            elif (self._loginterval_combo.get_active() == 3):
                self.logginginterval_status = '10minute'
            elif (self._loginterval_combo.get_active() == 4):
                self.logginginterval_status = '30minute'
            self._set_record_button_tooltip()
        return

    def _set_record_button_tooltip(self):
        """ Determines the tool tip for the record button. The tool tip
        text depends upon whether sampling is currently on and whether
        the sampling interval > 0. """
        if self._record == None:
            return
        if self.activity.LOGGING_IN_SESSION:
            self._record.set_tooltip(_('Stop sampling'))
        else:  # No sampling in progress
            if (self._loginterval_combo.get_active() == 0):
                self._record.set_tooltip(_('Capture sample now'))
            else:
                self._record.set_tooltip(_('Start sampling'))
        return

    def update_trigger_control(self, *args):
        """ Callback for trigger control """
        active = self._trigger_combo.get_active()
        if active == -1:
            return

        self.activity.wave.set_trigger(self.trigger_conf[active])
        return

    def _pauseplay_control_cb(self, data=None):
        """ Callback for Pause Button """
        if self.activity.audiograb.get_freeze_the_display():
            self.activity.audiograb.set_freeze_the_display(False)
            self._pause.set_icon('media-playback-pause-insensitive')
            self._pause.set_tooltip(_('Unfreeze the display'))
            self._pause.show()
        else:
            self.activity.audiograb.set_freeze_the_display(True)
            self._pause.set_icon('media-playback-pause')
            self._pause.set_tooltip(_('Freeze the display'))
            self._pause.show()
        return False

    def _timefreq_control_cb(self, data=None, time_state=True):
        """ Callback for Time and Freq. Buttons """

        # Make sure the current context is for sound capture.
        if self.activity.CONTEXT != 'sound':
            self.activity.set_sound_context()

        if time_state:
            self.activity.wave.set_fft_mode(False)
            self.time.set_icon('domain-time2')
            self.freq.set_icon('domain-freq')
            self.time.show()
            self.freq.show()
            self._update_string_for_textbox()
            if self.activity.has_toolbarbox:
                self.activity.label_button.set_icon('domain-time2')
                self.activity.label_button.set_tooltip(_('Time Base'))
        else:
            self.activity.wave.set_fft_mode(True)
            self.time.set_icon('domain-time')
            self.freq.set_icon('domain-freq2')
            self.time.show()
            self.freq.show()
            self._update_string_for_textbox()
            if self.activity.has_toolbarbox:
                self.activity.label_button.set_icon('domain-freq2')
                self.activity.label_button.set_tooltip(_('Frequency Base'))
        if self.activity.has_toolbarbox and \
                hasattr(self.activity, 'sensor_toolbar'):
            self.activity.sensor_toolbar.resistance.set_icon('bias-on')
            self.activity.sensor_toolbar.voltage.set_icon('bias-off')
        return False

    def _freq_stepper_up_cb(self, data=None):
        """Moves the horizontal zoom slider to the left one notch, where
        one notch is 1/100 of the total range. This correspond to zooming
        out as a larger number of Hertz or milliseconds will be
        represented by the same space on the screen."""
        new_value = self._freq_range.get_value() +\
                    (self.UPPER - self.LOWER) / 100.0
        if new_value <= self.UPPER:
            self._freq_range.set_value(new_value)
        else:
            self._freq_range.set_value(self.UPPER)

    def _freq_stepper_down_cb(self, data=None):
        """Moves the horizontal zoom slider to the right one notch, where
        one notch is 1/100 of the total range. This corresponds to zooming
        in."""
        new_value = self._freq_range.get_value() -\
                    (self.UPPER - self.LOWER) / 100.0
        if new_value >= self.LOWER:
            self._freq_range.set_value(new_value)
        else:
            self._freq_range.set_value(self.LOWER)

    def cb_page_sizef(self, data=None):
        """ Callback to scale the frequency range (zoom in and out) """
        if self._update_page_size_id:
            gobject.source_remove(self._update_page_size_id)
        self._update_page_size_id =\
            gobject.timeout_add(250, self.update_page_size)
        return True

    def update_page_size(self):
        """ Set up the scaling of the display """
        self._update_page_size_id = None

        new_value = round(self.activity.adjustmentf.value * 100.0) / 100.0
        if self.activity.adjustmentf.value != new_value:
            self.activity.adjustmentf.value = new_value
            return False

        time_div = 0.001*max(self.activity.adjustmentf.value, 0.05)
        freq_div = 1000*max(self.activity.adjustmentf.value, 0.01)

        self.activity.wave.set_div(time_div, freq_div)

        self._update_string_for_textbox()

        return False

    def context_off(self):
        """When some other context is switched to and the sound context 
        is switched off"""
        print "context off: gain and y_mag were %f and %f" %\
            (self.gain, self.y_mag)
        self.gain, self.y_mag = self.activity.wave.get_mag_params()
        print "context off: gain and y_mag are %f and %f" %\
            (self.gain, self.y_mag)
        self.capture_gain = self.activity.audiograb.get_capture_gain()
        self.mic_boost = self.activity.audiograb.get_mic_boost()
        print "context off: capture gain %s and mic boost %s" %\
              (str(self.capture_gain), str(self.mic_boost))
        self.activity.audiograb.stop_sound_device()
        self.activity.wave.set_fft_mode(False)

    def context_on(self):
        """When the sound context is switched on"""
        self.activity.audiograb.start_sound_device()
        self.activity.audiograb.set_sensor_type('sound')
        self.activity.wave.set_fft_mode(False)
        print "context on: gain and y_mag are %f and %f" %\
              (self.gain, self.y_mag)
        self.activity.wave.set_mag_params(self.gain, self.y_mag)
        self._update_string_for_textbox()
        self.update_trigger_control()
        return False

    def _update_string_for_textbox(self):
        """ Update the text at the bottom of the canvas """
        if not self.activity.wave.get_fft_mode():
            self._STR_SCALEX = self._STR_XAXIS_TEXT % \
                {'unit': self._ms,
                 'division': self.activity.wave.time_div*1000} 
        else:
            self._STR_SCALEX = self._STR_XAXIS_TEXT % \
                {'unit': self._Hz, 'division': self.activity.wave.freq_div} 

        self.string_for_textbox = ""
        self.string_for_textbox += (self._STR_BASIC + '\t')
        if not self.activity.wave.get_fft_mode():
            self.string_for_textbox += self._STR1
        else:
            self.string_for_textbox += self._STR2
        if self.activity.wave.get_invert_state():
            self.string_for_textbox += self._STR3
        self.string_for_textbox += ('\n' + self._STR_SCALEX)
        self.activity.text_box.set_data_params(0, self.string_for_textbox)
