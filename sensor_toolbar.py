# -*- coding: utf-8 -*-
#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2009, Walter Bender
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

import pygtk
import gtk
import time
from gettext import gettext as _

import config

from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.combobox import ComboBox
from sugar.graphics.toolcombobox import ToolComboBox
import logging
log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)
try:
    import gconf
except:
    from sugar import profile


class SensorToolbar(gtk.Toolbar):
    """ The toolbar for resitance and voltage sensors """

    def __init__(self, activity):
        """ By default, start with resistance mode """

        gtk.Toolbar.__init__(self)

        self.mode = 'resistance'

        self._STR_BASIC = \
        _("Sensors, DC (connect sensor to pink 'Mic In' on left side of XO)") \
        + " "
        self._STR_R = _("Bias/Offset Enabled") + " (Ω) "
        self._STR_V = _("Bias/Offset Disabled") + " (V) "
        self._STR_I = _(" Invert") + " "

        self.gain_state = None
        self.boost_state = None        

        # self.b = 0

        self.string_for_textbox = ""

        self.wave = activity.wave
        self.ag = activity.audiograb
        self.ag.set_sensor(self)
        self.textbox_copy = activity.text_box
        self.ji = activity.ji
    
        self.logging_status = False

        # Set up Resistance Button 
        self._resistance = ToolButton('bias-on2')
        self.insert(self._resistance, -1)
        self._resistance.show()
        self._resistance.set_tooltip(_('Resistance Sensor'))
        self._resistance.connect('clicked', self.set_resistance_voltage_mode,
                                 'resistance')

        # Set up Voltage Button
        self._voltage = ToolButton('bias-off')
        self.insert(self._voltage, -1)
        self._voltage.set_tooltip(_('Voltage Sensor'))
        self._voltage.connect('clicked', self.set_resistance_voltage_mode,
                              'voltage')

        # Set up Invert Button
        self._invert = ToolButton('invert')
        self.insert(self._invert, -1)
        self._invert.set_tooltip(_('Invert'))
        self._invert.connect('clicked', self._invert_control_cb)
        self.wave.set_invert_state(False)

        separator = gtk.SeparatorToolItem()
        separator.props.draw = True
        self.insert(separator, -1)

        # Set up Logging Interval combo box
        self.loginterval_img = gtk.Image()
        self.loginterval_img.set_from_file(config.ICONS_DIR+'/sample_rate.svg')
        self.loginterval_img_tool = gtk.ToolItem()
        self.loginterval_img_tool.add(self.loginterval_img)
        self.insert(self.loginterval_img_tool,-1)

        self._loginterval_combo = ComboBox()
        self.interval = [_('1/10 second'), _('1 second') , _('30 seconds'),
                         _('5 minutes'), _('30 minutes')]

        self._interval_changed_id = self._loginterval_combo.connect("changed",
                                         self.loginterval_control)

        for i, s in enumerate(self.interval):
            self._loginterval_combo.append_item(i, s, None)
            if s == _('1 second'):
                self._loginterval_combo.set_active(i)

        self._loginterval_tool = ToolComboBox(self._loginterval_combo)
        self.insert(self._loginterval_tool,-1)
        self.logginginterval_status = '1 second'		

        # Set up Logging/Stop Logging Button
        self._record = ToolButton('media-record')
        self.insert(self._record, -1)
        self._record.set_tooltip(_('Start Recording'))
        self._record.connect('clicked', self.record_control)

        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.insert(separator, -1)

        # A label for displaying the sample value
        self.sample_value = gtk.Label("")
        self.sample_value_toolitem = gtk.ToolItem()
        self.sample_value_toolitem.add(self.sample_value)
        self.insert(self.sample_value_toolitem, -1)

        self.show_all()

    def set_sample_value(self, label=""):
        """ Write a sample value to the toolbar label """
        self.sample_value.set_text(label)
        self.sample_value.show()

    def record_control(self, data=None):
        """Depending upon the selected interval, does either
        a logging session, or just logs the current buffer"""

        #   config.LOGGING_IN_SESSION appears to be a duplicate of
        #   self.logging_status.
	#
        if config.LOGGING_IN_SESSION == False:
            Xscale = (1.00/self.ag.get_sampling_rate())
            Yscale = 0.0
            interval = self.interval_convert()
            try:
                client = gconf.client_get_default()
                username = client.get_string("/desktop/suagr/user/nick")
            except:
                username = profile.get_nick_name()
            self.ji.start_new_session(username, Xscale, Yscale,
                                      self.logginginterval_status)
            self.ag.set_logging_params(True, interval, False)
            config.LOGGING_IN_SESSION = True
            self.logging_status = True
            self._record.set_icon('record-stop')
            self._record.show()
            self._record.set_tooltip(_('Stop Recording'))
        else:
            if self.logging_status == True: 
                self.ag.set_logging_params(False)
                time.sleep(0.2)
                self.ji.stop_session()                
                config.LOGGING_IN_SESSION = False
                self.logging_status = False
                self._record.set_icon('media-record')
                self._record.show()
                self._record.set_tooltip(_('Start Recording'))

    def interval_convert(self):
        """Converts interval string to an integer that denotes the number
        of times the audiograb buffer must be called before a value is written.
        When set to 0, the whole of current buffer will be written"""
        interval_dictionary = {'1/10 second':9, '1 second':89,
                               '30 seconds':2667,
                               '5 minutes':26667, '30 minutes':160000}
        try:
            return interval_dictionary[self.logginginterval_status]
        except:
            print "logging interval status = %s" %\
                  (str(self.logginginterval_status))
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
        self.set_mode(mode_to_set)
        if mode_to_set == 'resistance':
            self._resistance.set_icon('bias-on2')
            self._voltage.set_icon('bias-off')
            self._resistance.show()
            self._voltage.show()
            self._update_string_for_textbox()
            return False
        elif mode_to_set == 'voltage':
            self._resistance.set_icon('bias-on')
            self._voltage.set_icon('bias-off2')
            self._resistance.show()
            self._voltage.show()
            self._update_string_for_textbox()
            return False
        else:
            logging.error("unknown mode %s" % (mode_to_set))
            return False

    def _invert_control_cb(self, data=None):
        """ Callback for Invert Button """
        if self.wave.get_invert_state()==True:
            self.wave.set_invert_state(False)
            self._invert.set_icon('invert')
            self._invert.show()
        else:
            self.wave.set_invert_state(True)
            self._invert.set_icon('invert2')
            self._invert.show()
        self._update_string_for_textbox()
        return False

    def set_mode(self, mode='resistance'):
        """ Set the mixer settings to match the current mode. """
        self.mode = mode
        self.ag.set_sensor_type(self.mode)
        return 

    def context_off(self):
        """ Called when sensor toolbar is no longer selected. """
        self.ag.pause_grabbing()
        
    def context_on(self):
        """ Called when sensor toolbar is selected. """
        self.ag.resume_grabbing()
        self.ag.set_sensor_type(self.mode)
        self._update_string_for_textbox()
        self.wave.set_trigger(self.wave.TRIGGER_NONE)

    def _update_string_for_textbox(self):
        """ Update the status field at the bottom of the canvas. """
        self.string_for_textbox = ""
        self.string_for_textbox += (self._STR_BASIC + "\n")
        if self.mode == 'resistance':
            self.string_for_textbox += self._STR_R
        else:
            self.string_for_textbox += self._STR_V
        if self.wave.get_invert_state()==True:
            self.string_for_textbox += self._STR_I
        self.textbox_copy.set_data_params(0, self.string_for_textbox)
