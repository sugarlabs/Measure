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

from config import ICONS_DIR

from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.combobox import ComboBox
from sugar.graphics.toolcombobox import ToolComboBox
import logging
log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)


class SensorToolbar(gtk.Toolbar):
    """ The toolbar for resitance and voltage sensors """

    def __init__(self, activity):
        """ By default, start with resistance mode """

        gtk.Toolbar.__init__(self)

        self.mode = 'resistance'

        self._STR_BASIC = \
        _("Sensors, DC (connect sensor to pink 'Mic In' on left side of XO)") \
        + " "
        self._STR_R = _("Bias/Offset Enabled") + " " + _("Ohms") + " "
        self._STR_V = _("Bias/Offset Disabled") + " " + _("Volts") + " "
        self._STR_I = _(" Invert") + " "

        # self.gain_state = None
        # self.boost_state = None

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
        self.resistance.connect('clicked', self.set_resistance_voltage_mode,
                                 'resistance')

        # Set up Voltage Button
        self.voltage = ToolButton('bias-off')
        self.insert(self.voltage, -1)
        self.voltage.set_tooltip(_('Voltage Sensor'))
        self.voltage.connect('clicked', self.set_resistance_voltage_mode,
                              'voltage')

        # Set up Invert Button
        self._invert = ToolButton('invert')
        self.insert(self._invert, -1)
        self._invert.set_tooltip(_('Invert'))
        self._invert.connect('clicked', self._invert_control_cb)
        self.activity.wave.set_invert_state(False)

        separator = gtk.SeparatorToolItem()
        separator.props.draw = True
        self.insert(separator, -1)

        # Set up Logging Interval combo box
        self.loginterval_img = gtk.Image()
        self.loginterval_img.set_from_file(ICONS_DIR + '/sample_rate.svg')
        self.loginterval_img_tool = gtk.ToolItem()
        self.loginterval_img_tool.add(self.loginterval_img)
        self.insert(self.loginterval_img_tool, -1)

        self._loginterval_combo = ComboBox()
        self.interval = [_('1/10 second'), _('1 second'), _('30 seconds'),
                         _('5 minutes'), _('30 minutes')]

        self._interval_changed_id = self._loginterval_combo.connect("changed",
                                         self.loginterval_control)

        for i, s in enumerate(self.interval):
            self._loginterval_combo.append_item(i, s, None)
            if s == _('1 second'):
                self._loginterval_combo.set_active(i)

        self._loginterval_tool = ToolComboBox(self._loginterval_combo)
        self.insert(self._loginterval_tool, -1)
        self.logginginterval_status = '1 second'

        # Set up Logging/Stop Logging Button
        self._record = ToolButton('media-record')
        self.insert(self._record, -1)
        self._record.set_tooltip(_('Start Recording'))
        self._record.connect('clicked', self.record_control)

        self.show_all()

    def set_sample_value(self, label=None):
        """ Write a sample value to the textbox """
        gtk.threads_enter()
        self._update_string_for_textbox(label)
        gtk.threads_leave()
        return

    def record_control(self, data=None):
        """Depending upon the selected interval, does either
        a logging session, or just logs the current buffer"""

        if not self.activity.LOGGING_IN_SESSION:
            Xscale = (1.00 / self.activity.audiograb.get_sampling_rate())
            Yscale = 0.0
            interval = self.interval_convert()
            username = self.activity.nick
            self.activity.ji.start_new_session(username, Xscale, Yscale,
                                      self.logginginterval_status)
            self.activity.audiograb.set_logging_params(True, interval, False)
            self.activity.LOGGING_IN_SESSION = True
            self._record.set_icon('record-stop')
            self._record.show()
            self._record.set_tooltip(_('Stop Recording'))
        else:
            self.activity.audiograb.set_logging_params(False)
            gobject.timeout_add(250, self.activity.ji.stop_session)
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
            logging.error("logging interval status = %s" %\
                              (str(self.logginginterval_status)))
            return 0

    def loginterval_control(self, combobox):
        """ Callback from the Logging Interval Combo box: sets status """
        if self._loginterval_combo.get_active() != -1:
            intervals = ['1/10 second', '1 second', '30 seconds',
                         '5 minutes', '30 minutes']
            self.logginginterval_status = \
                              intervals[self._loginterval_combo.get_active()]

    def set_resistance_voltage_mode(self, data=None, mode_to_set='resistance'):
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
                self.activity.mode_image.set_from_file(ICONS_DIR +\
                                                           '/bias-on2.svg')
                self.activity.label.set_text(" " + _('Resistance Sensor'))
        elif mode_to_set == 'voltage':
            self.resistance.set_icon('bias-on')
            self.voltage.set_icon('bias-off2')
            self.resistance.show()
            self.voltage.show()
            self._update_string_for_textbox()
            if self.activity.has_toolbarbox:
                self.activity.mode_image.set_from_file(ICONS_DIR +\
                                                           '/bias-off2.svg')
                self.activity.label.set_text(" " + _('Voltage Sensor'))
        else:
            logging.error("unknown mode %s" % (mode_to_set))
        if self.activity.has_toolbarbox:
            self.activity.sound_toolbar.time.set_icon('domain-time')
            self.activity.sound_toolbar.freq.set_icon('domain-freq')
        return False

    def _invert_control_cb(self, data=None):
        """ Callback for Invert Button """
        if self.activity.wave.get_invert_state():
            self.activity.wave.set_invert_state(False)
            self._invert.set_icon('invert')
            self._invert.show()
        else:
            self.activity.wave.set_invert_state(True)
            self._invert.set_icon('invert2')
            self._invert.show()
        self._update_string_for_textbox()
        return False

    def set_mode(self, mode='resistance'):
        """ Set the mixer settings to match the current mode. """
        self.mode = mode
        self.activity.audiograb.set_sensor_type(self.mode)
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

    def _update_string_for_textbox(self, value=None):
        """ Update the status field at the bottom of the canvas. """
        self.string_for_textbox = ""
        self.string_for_textbox += (self._STR_BASIC + "\n")
        if self.mode == 'resistance':
            self.string_for_textbox += self._STR_R
        else:
            self.string_for_textbox += self._STR_V
        if self.activity.wave.get_invert_state():
            self.string_for_textbox += self._STR_I
        if value is not None:
            self.string_for_textbox += "\t(%s)" % (str(value))
        self.activity.text_box.set_data_params(0, self.string_for_textbox)
