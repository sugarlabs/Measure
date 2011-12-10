# -*- coding: utf-8 -*-
#! /usr/bin/python
#
# Author:  Arjun Sarwal   arjun@laptop.org
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


import gtk
import gobject
import os
from gettext import gettext as _

from config import ICONS_DIR

from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.combobox import ComboBox
from sugar.graphics.toolcombobox import ToolComboBox
import logging
log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)


class SensorToolbar(gtk.Toolbar):
    """ The toolbar for resitance and voltage sensors """

    def __init__(self, activity, channels):
        """ By default, start with resistance mode """

        gtk.Toolbar.__init__(self)

        self.mode = 'resistance'
        self._channels = channels
        self.values = []
        for i in range(self._channels):
            self.values.append(0.0)

        self._STR_BASIC = \
        _("Sensors, DC (connect sensor to pink 'Mic In' on left side of XO)") \
        + ' '
        self._STR_R = _('Bias/Offset Enabled') + ' ' + _('Ohms') + ' '
        self._STR_V = _('Bias/Offset Disabled') + ' ' + _('Volts') + ' '
        self._STR_I = ' ' + _('Invert') + ' '

        self.string_for_textbox = ""

        self.activity = activity
        self.activity.audiograb.set_sensor(self)

        # Set up Resistance Button
        if self.activity.has_toolbarbox:
            self.resistance = ToolButton('bias-on')
        else:
            self.resistance = ToolButton('bias-on2')
        self.insert(self.resistance, -1)
        self.resistance.show()
        self.resistance.set_tooltip(_('Resistance Sensor'))
        self.resistance.connect('clicked', self.resistance_voltage_mode_cb,
                                 'resistance')

        # Set up Voltage Button
        self.voltage = ToolButton('bias-off')
        self.insert(self.voltage, -1)
        self.voltage.set_tooltip(_('Voltage Sensor'))
        self.voltage.connect('clicked', self.resistance_voltage_mode_cb,
                              'voltage')

        separator = gtk.SeparatorToolItem()
        separator.props.draw = True
        self.insert(separator, -1)

        # Set up Logging Interval combo box
        self.log_interval_img = gtk.Image()
        self.log_interval_img.set_from_file(os.path.join(ICONS_DIR,
                                                        'sample_rate.svg'))
        self.log_interval_img_tool = gtk.ToolItem()
        self.log_interval_img_tool.add(self.log_interval_img)
        self.insert(self.log_interval_img_tool, -1)

        self._log_interval_combo = ComboBox()
        self.interval = [_('1/10 second'), _('1 second'), _('30 seconds'),
                         _('5 minutes'), _('30 minutes')]

        if hasattr(self._log_interval_combo, 'set_tooltip_text'):
            self._log_interval_combo.set_tooltip_text(_('Sampling interval'))

        self._interval_changed_id = self._log_interval_combo.connect("changed",
                                         self.log_interval_cb)

        for i, s in enumerate(self.interval):
            self._log_interval_combo.append_item(i, s, None)
            if s == _('1 second'):
                self._log_interval_combo.set_active(i)

        self._log_interval_tool = ToolComboBox(self._log_interval_combo)
        self.insert(self._log_interval_tool, -1)
        self.logginginterval_status = '1 second'

        # Set up Logging/Stop Logging Button
        self._record = ToolButton('media-record')
        self.insert(self._record, -1)
        self._record.set_tooltip(_('Start Recording'))
        self._record.connect('clicked', self.record_control_cb)

        self.show_all()

    def set_sample_value(self, value=0.0, channel=0):
        """ Write a sample value to the textbox """
        gtk.threads_enter()
        self.values[channel] = value
        self._update_string_for_textbox()
        gtk.threads_leave()
        return

    def record_control_cb(self, button=None):
        """Depending upon the selected interval, does either a logging
        session, or just logs the current buffer"""

        if not self.activity.LOGGING_IN_SESSION:
            Xscale = (1.00 / self.activity.audiograb.get_sampling_rate())
            Yscale = 0.0
            interval = self.interval_convert()
            username = self.activity.nick
            self.activity.ji.start_new_session(
                username, Xscale, Yscale, _(self.logginginterval_status),
                channels=self._channels)
            self.activity.audiograb.set_logging_params(True, interval, False)
            self.activity.LOGGING_IN_SESSION = True
            self._record.set_icon('record-stop')
            self._record.show()
            self._record.set_tooltip(_('Stop Recording'))
        else:
            self.activity.audiograb.set_logging_params(False)
            self.activity.LOGGING_IN_SESSION = False
            self._record.set_icon('media-record')
            self._record.show()
            self._record.set_tooltip(_('Start Recording'))

    def interval_convert(self):
        """Converts interval string to an integer that denotes the number
        of times the audiograb buffer must be called before a value is written.
        When set to 0, the whole of current buffer will be written"""
        interval_dictionary = {'1/10 second': 0.1, '1 second': 1,
                               '30 seconds': 30,
                               '5 minutes': 300, '30 minutes': 1800}
        try:
            return interval_dictionary[self.logginginterval_status]
        except ValueError:
            logging.error('logging interval status = %s' %\
                              (str(self.logginginterval_status)))
            return 0

    def log_interval_cb(self, combobox):
        """ Callback from the Logging Interval Combo box: sets status """
        if self._log_interval_combo.get_active() != -1:
            intervals = ['1/10 second', '1 second', '30 seconds',
                         '5 minutes', '30 minutes']
            self.logginginterval_status = \
                              intervals[self._log_interval_combo.get_active()]

    def resistance_voltage_mode_cb(self, button=None,
                                   mode_to_set='resistance'):
        """ Callback for Resistance/Voltage Buttons """

        # Make sure the current context is for sensor capture.
        if self.activity.CONTEXT != 'sensor':
            self.activity.set_sensor_context()

        self.set_mode(mode_to_set)
        if mode_to_set == 'resistance':
            self.resistance.set_icon('bias-on2')
            self.voltage.set_icon('bias-off')
            self.resistance.show()
            self.voltage.show()
            self._update_string_for_textbox()
            if self.activity.has_toolbarbox:
                self.activity.label_button.set_icon('bias-on2')
                self.activity.label_button.set_tooltip(_('Resistance Sensor'))
        elif mode_to_set == 'voltage':
            self.resistance.set_icon('bias-on')
            self.voltage.set_icon('bias-off2')
            self.resistance.show()
            self.voltage.show()
            self._update_string_for_textbox()
            if self.activity.has_toolbarbox:
                self.activity.label_button.set_icon('bias-off2')
                self.activity.label_button.set_tooltip(_('Voltage Sensor'))
        else:
            logging.error('unknown mode %s' % (mode_to_set))
        if self.activity.has_toolbarbox:
            self.activity.sound_toolbar.time.set_icon('domain-time')
            self.activity.sound_toolbar.freq.set_icon('domain-freq')
        return False

    def set_mode(self, mode='resistance'):
        """ Set the mixer settings to match the current mode. """
        self.mode = mode
        self.activity.audiograb.set_sensor_type(self.mode)
        for i in range(self._channels):
            self.values[i] = 0.0
        return

    def context_off(self):
        """ Called when sensor toolbar is no longer selected. """
        self.activity.audiograb.pause_grabbing()

    def context_on(self):
        """ Called when sensor toolbar is selected. """
        self.activity.audiograb.resume_grabbing()
        self.activity.audiograb.set_sensor_type(self.mode)
        self._update_string_for_textbox()
        self.activity.wave.set_trigger(self.activity.wave.TRIGGER_NONE)
        return False

    def _update_string_for_textbox(self, channel=0):
        """ Update the status field at the bottom of the canvas. """
        self.string_for_textbox = ""
        self.string_for_textbox += (self._STR_BASIC + "\n")
        if self.mode == 'resistance':
            self.string_for_textbox += self._STR_R
        else:
            self.string_for_textbox += self._STR_V
        if self.activity.wave.get_invert_state():
            self.string_for_textbox += self._STR_I
        for i in range(self._channels):
            self.string_for_textbox += '\t(%0.3f)' % (self.values[i])
        self.activity.text_box.set_data_params(0, self.string_for_textbox)
