# -*- coding: utf-8 -*-
#! /usr/bin/python
#
# Author:  Arjun Sarwal   arjun@laptop.org
# Copyright (C) 2007, Arjun Sarwal
# Copyright (C) 2009-13 Walter Bender
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


import gtk
import gobject
import os
from gettext import gettext as _
from gettext import ngettext

from config import ICONS_DIR, CAPTURE_GAIN, MIC_BOOST, XO1, XO15, XO175, XO4

from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.menuitem import MenuItem
from sugar.graphics.radiotoolbutton import RadioToolButton
import logging
log = logging.getLogger('measure-activity')
log.setLevel(logging.DEBUG)

LOG_TIMER_VALUES = [1, 10, 300, 3000, 18000]  # In 10th second intervals
LOG_TIMER_LABELS = {1: _('1/10 second'), 10: _('1 second'),
                    300: _('30 seconds'), 3000: _('5 minutes'),
                    30000: _('30 minutes')}


def _is_xo(hw):
    ''' Return True if this is xo hardware '''
    return hw in [XO1, XO15, XO175, XO4]


class SensorToolbar(gtk.Toolbar):
    ''' The toolbar for specifiying the sensor: sound, resitance, or
    voltage '''

    LOWER = 0.0
    UPPER = 1.0
    STR_DC_R = \
        _("Resistive sensor (connect sensor to pink 'Mic In' on left side \
of XO)") + ' '
    STR_DC_V = \
        _("Voltage sensor (connect sensor to pink 'Mic In' on left side \
of XO)") + ' '
    STR_AC = _('Sound') + ' '
    STR_RESISTANCE = _('Resistance') + ' (' + _('Ohms') + ') '
    STR_VOLTAGE = _('Voltage') + ' (' + _('Volts') + ') '
    STR_TIME = _('Time Base') + ' '
    STR_FREQUENCY = _('Frequency Base') + ' '
    STR_INVERT = ' ' + _('Invert') + ' '
    STR_XAXIS_TEXT = _('X Axis Scale: 1 division = %(division)s %(unit)s')
    # TRANSLATORS: This is milli seconds.
    MS = _('ms')
    # TRANSLATORS: This is Hertz, so 1/second.
    HZ = _('Hz')

    def __init__(self, activity, channels):
        ''' By default, start with resistance mode '''

        gtk.Toolbar.__init__(self)

        self.activity = activity
        self._channels = channels
        self._lock_radio_buttons = False
        self._radio_button_pushed = False
        self.values = []
        for i in range(self._channels):
            self.values.append('')

        self.string_for_textbox = ''

        self.gain = 1.0
        self.y_mag = 3.0
        self.capture_gain = CAPTURE_GAIN
        self.mic_boost = MIC_BOOST

        self.mode = 'sound'

        # Set up Time-domain Button
        self.time = RadioToolButton(group=None)
        self.time.set_named_icon('media-audio')
        self.insert(self.time, -1)
        self.time.set_tooltip(_('Sound'))
        self.time.connect(
            'clicked', self.analog_resistance_voltage_mode_cb, 'sound')

        # Set up Resistance Button
        self.resistance = RadioToolButton(group=self.time)
        self.resistance.set_named_icon('resistance')
        if _is_xo(self.activity.hw):
            self.insert(self.resistance, -1)
        self.resistance.show()
        self.resistance.set_tooltip(_('Resistance Sensor'))
        self.resistance.connect('clicked',
                                self.analog_resistance_voltage_mode_cb,
                                'resistance')

        # Set up Voltage Button
        self.voltage = RadioToolButton(group=self.time)
        self.voltage.set_named_icon('voltage')
        if _is_xo(self.activity.hw):
            self.insert(self.voltage, -1)
        self.voltage.set_tooltip(_('Voltage Sensor'))
        self.voltage.connect('clicked',
                             self.analog_resistance_voltage_mode_cb,
                             'voltage')

        separator = gtk.SeparatorToolItem()
        separator.props.draw = True
        self.insert(separator, -1)

        self._log_value = LOG_TIMER_VALUES[1]
        self.log_label = gtk.Label(self._log_to_string(self._log_value))
        toolitem = gtk.ToolItem()
        toolitem.add(self.log_label)
        self.insert(toolitem, -1)

        self._log_button = ToolButton('timer-10')
        self._log_button.set_tooltip(_('Select logging interval'))
        self._log_button.connect('clicked', self._log_selection_cb)
        self.insert(self._log_button, -1)
        self._setup_log_palette()

        # Set up Logging/Stop Logging Button
        self._record = ToolButton('media-record')
        self.insert(self._record, -1)
        self._record.set_tooltip(_('Start logging'))
        self._record.connect('clicked', self.record_control_cb)

        separator = gtk.SeparatorToolItem()
        separator.props.draw = True
        self.insert(separator, -1)

        toolitem = gtk.ToolItem()
        self.trigger_label = gtk.Label(_('Trigger'))
        toolitem.add(self.trigger_label)
        self.insert(toolitem, -1)

        # Set up Trigger Combo box
        self.trigger_none = RadioToolButton()
        self.trigger_none.set_named_icon('trigger-none')
        self.insert(self.trigger_none, -1)
        self.trigger_none.set_tooltip(_('None'))
        self.trigger_none.connect('clicked',
                                  self.update_trigger_control_cb,
                                  self.activity.wave.TRIGGER_NONE)

        self.trigger_rise = RadioToolButton(group=self.trigger_none)
        self.trigger_rise.set_named_icon('trigger-rise')
        self.insert(self.trigger_rise, -1)
        self.trigger_rise.set_tooltip(_('Rising Edge'))
        self.trigger_rise.connect('clicked',
                                  self.update_trigger_control_cb,
                                  self.activity.wave.TRIGGER_POS)

        self.trigger_fall = RadioToolButton(group=self.trigger_none)
        self.trigger_fall.set_named_icon('trigger-fall')
        self.insert(self.trigger_fall, -1)
        self.trigger_fall.set_tooltip(_('Falling Edge'))
        self.trigger_fall.connect('clicked',
                                  self.update_trigger_control_cb,
                                  self.activity.wave.TRIGGER_NEG)

        self.show_all()

    def get_log(self):
        return self._log_value

    def get_log_idx(self):
        if self._log_value in LOG_TIMER_VALUES:
            return LOG_TIMER_VALUES.index(self._log_value)
        else:
            return LOG_TIMER_VALUES[0]

    def set_log_idx(self, idx):
        self._log_value = LOG_TIMER_VALUES[idx]
        self.log_label.set_text(self._log_to_string(self._log_value))
        if hasattr(self, '_log_button'):
            self._log_button.set_icon('timer-%d' % (self._log_value))

    def _log_selection_cb(self, widget):
        if self._log_palette:
            if not self._log_palette.is_up():
                self._log_palette.popup(immediate=True,
                                    state=self._log_palette.SECONDARY)
            else:
                self._log_palette.popdown(immediate=True)
            return

    def _log_to_seconds(self, tenth_seconds):
        return tenth_seconds / 10.

    def _log_to_string(self, tenth_seconds):
        if tenth_seconds in LOG_TIMER_LABELS:
            return LOG_TIMER_LABELS[tenth_seconds]
        else:
            return _('1 second')

    def _setup_log_palette(self):
        self._log_palette = self._log_button.get_palette()

        for tenth_seconds in LOG_TIMER_VALUES:
            text = self._log_to_string(tenth_seconds)
            menu_item = MenuItem(icon_name='timer-%d' % (tenth_seconds),
                                 text_label=self._log_to_string(tenth_seconds))
            menu_item.connect('activate', self._log_selected_cb, tenth_seconds)
            self._log_palette.menu.append(menu_item)
            menu_item.show()

    def _log_selected_cb(self, button, seconds):
        self.set_log_idx(LOG_TIMER_VALUES.index(seconds))

    def add_frequency_slider(self, toolbox):
        ''' Either on the Sound toolbar or the Main toolbar '''
        self._freq_stepper_up = ToolButton('freq-high')
        self._freq_stepper_up.set_tooltip(_('Zoom out'))
        self._freq_stepper_up.connect('clicked', self._freq_stepper_up_cb)
        self._freq_stepper_up.show()

        self.activity.adjustmentf = gtk.Adjustment(
            0.5, self.LOWER, self.UPPER, 0.01, 0.1, 0)
        self.activity.adjustmentf.connect('value_changed', self.cb_page_sizef)

        self._freq_range = gtk.HScale(self.activity.adjustmentf)
        self._freq_range.set_inverted(True)
        self._freq_range.set_draw_value(False)
        self._freq_range.set_update_policy(gtk.UPDATE_CONTINUOUS)
        self._freq_range.set_size_request(120, 15)
        self._freq_range.show()

        self._freq_stepper_down = ToolButton('freq-low')
        self._freq_stepper_down.set_tooltip(_('Zoom in'))
        self._freq_stepper_down.connect('clicked', self._freq_stepper_down_cb)
        self._freq_stepper_down.show()

        self._freq_range_tool = gtk.ToolItem()
        self._freq_range_tool.add(self._freq_range)
        self._freq_range_tool.show()

        toolbox.add(self._freq_stepper_up)
        toolbox.add(self._freq_range_tool)
        toolbox.add(self._freq_stepper_down)
        return

    def update_trigger_control_cb(self, button, value):
        if button is None:
            value = self.activity.wave.TRIGGER_NONE
        if self.activity.wave.get_fft_mode():
            self.trigger_none.set_active(True)
        else:
            self.activity.wave.set_trigger(value)

    def analog_resistance_voltage_mode_cb(self, button=None,
                                   mode_to_set='sound'):
        ''' Callback for Analog/Resistance/Voltage Buttons '''
        if self._lock_radio_buttons:
            logging.debug('mode selector locked')
            self._radio_button_pushed = True
            return
        if self.mode == mode_to_set:
            logging.debug('mode already set to %s' % mode_to_set)
            return
        self._lock_radio_buttons = True
        if self.activity.CONTEXT == 'sound':
            self.sound_context_off()
        else:
            self.sensor_context_off()

        # Force time domain when switching modes
        if self.activity.wave.get_fft_mode():
            self.activity.timefreq_control()
        # Turn off logging when switching modes
        if self.activity.audiograb.we_are_logging:
            self.record_control_cb()

        self.set_mode(mode_to_set)
        if mode_to_set == 'sound':
            self.set_sound_context()
        elif mode_to_set == 'resistance':
            self.set_sensor_context()
        elif mode_to_set == 'voltage':
            self.set_sensor_context()
        self.update_string_for_textbox()
        return False

    def unlock_radio_buttons(self):
        ''' Enable radio button selection '''
        logging.debug('unlocking radio buttons')
        if self._radio_button_pushed:
            if self.mode == 'sound':
                self.time.set_active(True)
            elif self.mode == 'resistance':
                self.resistance.set_active(True)
            elif self.mode == 'voltage':
                self.voltage.set_active(True)
        self._lock_radio_buttons = False
        self._radio_button_pushed = False

    def set_mode(self, mode='sound'):
        ''' Set the mixer settings to match the current mode. '''
        self.mode = mode
        self.activity.audiograb.set_sensor_type(self.mode)
        for i in range(self._channels):
            self.values[i] = 0.0
        return

    def get_mode(self):
        ''' Get the mixer settings. '''
        return self.mode

    def _freq_stepper_up_cb(self, button=None):
        ''' Moves the horizontal zoom slider to the left one notch,
        where one notch is 1/100 of the total range. This correspond
        to zooming out as a larger number of Hertz or milliseconds
        will be represented by the same space on the screen. '''
        new_value = self._freq_range.get_value() +\
                    (self.UPPER - self.LOWER) / 100.0
        if new_value <= self.UPPER:
            self._freq_range.set_value(new_value)
        else:
            self._freq_range.set_value(self.UPPER)

    def _freq_stepper_down_cb(self, button=None):
        ''' Moves the horizontal zoom slider to the right one notch,
        where one notch is 1/100 of the total range. This corresponds
        to zooming in. '''
        new_value = self._freq_range.get_value() -\
                    (self.UPPER - self.LOWER) / 100.0
        if new_value >= self.LOWER:
            self._freq_range.set_value(new_value)
        else:
            self._freq_range.set_value(self.LOWER)

    def cb_page_sizef(self, button=None):
        ''' Callback to scale the frequency range (zoom in and out) '''
        if self._update_page_size_id:
            gobject.source_remove(self._update_page_size_id)
        self._update_page_size_id =\
            gobject.timeout_add(250, self.update_page_size)
        return True

    def update_page_size(self):
        ''' Set up the scaling of the display. '''
        self._update_page_size_id = None
        new_value = round(self.activity.adjustmentf.value * 100.0) / 100.0
        if self.activity.adjustmentf.value != new_value:
            self.activity.adjustmentf.value = new_value
            return False
        time_div = 0.001 * max(self.activity.adjustmentf.value, 0.05)
        freq_div = 1000 * max(self.activity.adjustmentf.value, 0.01)
        self.activity.wave.set_div(time_div, freq_div)
        self.update_string_for_textbox()
        return False

    def set_sound_context(self):
        ''' Called when analog sensing is selected '''
        self.set_show_hide_windows(mode='sound')
        gobject.timeout_add(500, self.sound_context_on)
        self.activity.CONTEXT = 'sound'

    def set_sensor_context(self):
        ''' Called when digital sensing is selected '''
        self.set_show_hide_windows(mode='sensor')
        gobject.timeout_add(500, self.sensor_context_on)
        self.activity.CONTEXT = 'sensor'

    def set_show_hide_windows(self, mode='sound'):
        ''' Shows the appropriate window identified by the mode '''
        self.activity.wave.set_context_on()
        for i in range(self._channels):
            self.activity.side_toolbars[i].set_show_hide(True, mode)

    def sensor_context_off(self):
        ''' Called when a DC sensor is no longer selected '''
        # self.activity.audiograb.pause_grabbing()
        self.activity.audiograb.stop_grabbing()

    def sensor_context_on(self):
        ''' Called when a DC sensor is selected '''
        self.update_string_for_textbox()
        self.activity.wave.set_trigger(self.activity.wave.TRIGGER_NONE)
        # self.activity.audiograb.resume_grabbing()
        self.activity.audiograb.start_grabbing()
        return False

    def sound_context_off(self):
        ''' Called when an analog sensor is no longer selected '''
        self.gain, self.y_mag = self.activity.wave.get_mag_params()
        self.capture_gain = self.activity.audiograb.get_capture_gain()
        self.mic_boost = self.activity.audiograb.get_mic_boost()
        self.activity.audiograb.stop_grabbing()

    def sound_context_on(self):
        ''' Called when an analog sensor is selected '''
        self.activity.wave.set_mag_params(self.gain, self.y_mag)
        self.update_string_for_textbox()
        self.update_trigger_control_cb(None, self.activity.wave.TRIGGER_NONE)
        self.activity.audiograb.start_grabbing()
        return False

    def set_sample_value(self, value='', channel=0):
        ''' Write a sample value to the textbox. '''
        gtk.threads_enter()
        self.values[channel] = value
        self.update_string_for_textbox()
        gtk.threads_leave()
        return

    def record_control_cb(self, button=None):
        ''' Depending upon the selected interval, does either a logging
        session, or just logs the current buffer. '''
        if self.activity.audiograb.we_are_logging:
            self.activity.audiograb.set_logging_params(start_stop=False)
            self._record.set_icon('media-record')
            self._record.show()
            self._record.set_tooltip(_('Start Recording'))
        else:
            Xscale = (1.00 / self.activity.audiograb.get_sampling_rate())
            Yscale = 0.0
            interval = self._log_value / 10. # self.interval_convert()
            username = self.activity.nick
            if self.activity.wave.get_fft_mode():
                self.activity.data_logger.start_new_session(
                    username, Xscale, Yscale,
                    self._log_to_string(self._log_value),
                    channels=self._channels, mode='frequency')
            else:
                self.activity.data_logger.start_new_session(
                    username, Xscale, Yscale,
                    self._log_to_string(self._log_value),
                    channels=self._channels, mode=self.mode)
            self.activity.audiograb.set_logging_params(
                start_stop=True, interval=interval, screenshot=False)
            self._record.set_icon('record-stop')
            self._record.show()
            self._record.set_tooltip(_('Stop Recording'))
            self.activity.new_recording = True

    def update_string_for_textbox(self):
        ''' Update the status field at the bottom of the canvas. '''
        if self.mode == 'resistance':
            string_for_textbox = (self.STR_DC_R + '\n')
            string_for_textbox += self.STR_RESISTANCE
        elif self.mode == 'voltage':
            string_for_textbox = (self.STR_DC_V + '\n')
            string_for_textbox += self.STR_VOLTAGE
        else:
            string_for_textbox = (self.STR_AC + '\t')
        if self.activity.wave.get_fft_mode():
            scalex = self.STR_XAXIS_TEXT % {
                'unit': self.HZ, 'division': self.activity.wave.freq_div}
            string_for_textbox += self.STR_FREQUENCY
            string_for_textbox += ('\n' + scalex)
        elif self.mode == 'sound':
            scalex = self.STR_XAXIS_TEXT % {
                    'unit': self.MS,
                    'division': self.activity.wave.time_div * 1000}
            string_for_textbox += self.STR_TIME
            string_for_textbox += ('\n' + scalex)
        else:
            for i in range(self._channels):
                string_for_textbox += '\t(%s)' % (self.values[i])
        invert = False
        for i in range(self._channels):
            if self.activity.wave.get_invert_state(channel=i):
                invert = True
        if invert:
            string_for_textbox += self.STR_INVERT
        self.activity.text_box.set_label(string_for_textbox)
