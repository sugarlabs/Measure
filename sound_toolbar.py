#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2009, Walter Bender
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
import gconf
from time import *
from gettext import gettext as _

import config  	#This has all the globals

from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.combobox import ComboBox
from sugar.graphics.toolcombobox import ToolComboBox
from sugar import profile

class SoundToolbar(gtk.Toolbar):

    def __init__(self, wave, audiograb, textbox, journal):

        gtk.Toolbar.__init__(self)

        self.wave = wave
        self.ag = audiograb
        self.textbox_copy = textbox
        self.ji = journal

        self._STR_BASIC = _("Sound ")
        self._STR1 = _("Time Base      ")
        self._STR2 = _("Frequency Base ")
        self._STR3 = _(" Invert ")
        self._STR_SCALEX = ""
        self._STR_XAXIS1 = _("X Axis Scale: 1 division = ")
        self._STR_XAXIS2 = _("ms ")
        self._STR_XAXIS3 = _("Hz ")

        self.string_for_textbox = ""

        self.g = 1.0
        self.y_mag = 3.0
        self.capture_gain = config.CAPTURE_GAIN
        self.mic_boost = config.MIC_BOOST

        self.logging_status = False

        ###################### time ########################
        self._time = ToolButton('domain-time2')
        self.insert(self._time, -1)
        self._time.show()
        self._time.set_tooltip(_('Time base'))
        self._time.connect('clicked', self._timefreq_control_cb, True)
        ####################################################

        ###################### frequency ###################
        self._freq = ToolButton('domain-freq')
        self.insert(self._freq, -1)
        self._freq.show()
        self._freq.set_tooltip(_('Frequency base'))
        self._freq.connect('clicked', self._timefreq_control_cb, False)
        ####################################################

        #self.time_freq_state = self.wave.get_fft_mode()
        #self._time.set_active(not(self.time_freq_state))
        #self._freq.set_active(self.time_freq_state)

        self.freq_low_img = gtk.Image()
        self.freq_high_img = gtk.Image()

        self.freq_low_img.set_from_file(config.ICONS_DIR + '/freq-high.svg')
        self.freq_high_img.set_from_file(config.ICONS_DIR + '/freq-low.svg')

        self.freq_low_img_tool = gtk.ToolItem()
        self.freq_high_img_tool = gtk.ToolItem()

        self.freq_low_img_tool.add(self.freq_low_img)
        self.freq_high_img_tool.add(self.freq_high_img)

        ################ frequency control #################
        self.adjustmentf = gtk.Adjustment(70, 10, 70 ,20, 20, 0.0)
        self.adjustmentf.connect("value_changed", self.cb_page_sizef, \
                                 self.adjustmentf)
        self._freq_range = gtk.HScale(self.adjustmentf)
        self._freq_range.set_draw_value(False)
        self._freq_range.set_update_policy(gtk.UPDATE_CONTINUOUS)
        self._freq_range.set_size_request(120,15)
        self._freq_range_tool = gtk.ToolItem()
        self._freq_range_tool.add(self._freq_range)
        ####################################################

        self.insert(self.freq_low_img_tool,-1)
        self.insert(self._freq_range_tool, -1)
        self.insert(self.freq_high_img_tool,-1)		

        self.freq_low_img.show()
        self.freq_high_img.show()

        self.freq_low_img_tool.show()
        self.freq_high_img_tool.show()

        separator = gtk.SeparatorToolItem()
        separator.props.draw = True
        self.insert(separator, -1)
        separator.show()

        ################## pause button ####################
        self._pause = ToolButton('media-playback-pause')
        self.insert(self._pause, -1)
        self._pause.show()
        self._pause.set_tooltip(_('Freeze the display'))
        self._pause.connect('clicked', self._pauseplay_control_cb)
        ####################################################

        separator = gtk.SeparatorToolItem()
        separator.props.draw = True
        self.insert(separator, -1)
        separator.show()

        self.loginterval_img = gtk.Image()
        self.loginterval_img.set_from_file(config.ICONS_DIR + \
                                           '/sample_rate.svg')
        self.loginterval_img_tool = gtk.ToolItem()
        self.loginterval_img_tool.add(self.loginterval_img)
        self.insert(self.loginterval_img_tool,-1)
        self.loginterval_img.show()
        self.loginterval_img_tool.show()

        ################# Logging Interval #################
        self._loginterval_combo = ComboBox()
        self.interval = [_('Now'), _('30 seconds') , _('2 minutes'),  \
                         _('10 minutes') , _('30 minutes') ]

        self._interval_changed_id = self._loginterval_combo.connect("changed",\
                                         self.loginterval_control)

        for i, s in enumerate(self.interval):
            self._loginterval_combo.append_item(i, s, None)
            if s == 'Now':
                self._loginterval_combo.set_active(i)

        self._loginterval_tool = ToolComboBox(self._loginterval_combo)
        self.insert(self._loginterval_tool,-1)
        self._loginterval_tool.show()
        self.logginginterval_status = 'picture'		
        ####################################################

        ############## Start Logging/Stop Logging ##########
        self._record = ToolButton('media-record')
        self.insert(self._record, -1)
        self._record.show()
        self._record.set_tooltip(_('Start Recording'))
        self._record.connect('clicked', self.record_control)
        ####################################################

    def record_control(self, data=None):
        """Depending upon the selected interval, does either
        a logging session, or just logs the current buffer"""
        if config.LOGGING_IN_SESSION == False:
            Xscale = (1.00/self.ag.get_sampling_rate())
            Yscale = 0.0
            interval = self.interval_convert()
            try:
                client = gconf.client_get_default()
                username = client.get_string("/desktop/suagr/user/nick")
            except:
                username = profile.get_nick_name()
            self.ji.start_new_session(username, Xscale, Yscale,\
                                      self.logginginterval_status)
            self.ag.set_logging_params(True, interval, True)
            config.LOGGING_IN_SESSION = True
            self.logging_status = True
            self._record.set_icon('record-stop')
            self._record.show()
            self._record.set_tooltip(_('Stop Recording'))
            if interval==0:
                self._record.set_icon('media-record')
                self._record.show()
                self._record.set_tooltip(_('Start Recording'))
                self.record_state = False
		config.LOGGING_IN_SESSION = False
		self.logging_status = False
        else:
            if self.logging_status == True:
                self.ag.set_logging_params(False)
                config.LOGGING_IN_SESSION = False
                self.logging_status = False
                self._record.set_icon('media-record')
                self._record.show()
                self._record.set_tooltip(_('Start Recording'))

    def interval_convert(self):
        """Converts picture/time interval to an integer which denotes the number
        of times the audiograb buffer must be called before a value is written.
        When set to 0, the whole of current buffer will be written
        1second= about 66 ticks at 48khz sampling"""
        if self.logginginterval_status == 'picture':
            return 0
        elif self.logginginterval_status == '30second':
            return 2667
        elif self.logginginterval_status == '2minute':
            return 10668
        elif self.logginginterval_status == '10minute':
            return 53340
        elif self.logginginterval_status == '30minute':
            return 160000

    def loginterval_control(self, combobox):
        if (self._loginterval_combo.get_active() != -1):
            if (self._loginterval_combo.get_active() == 0):
                self.logginginterval_status = 'picture'		
            if (self._loginterval_combo.get_active() == 1):
                self.logginginterval_status = '30second'		
            if (self._loginterval_combo.get_active() == 2):
                self.logginginterval_status = '2minute'		
            if (self._loginterval_combo.get_active() == 3):
                self.logginginterval_status = '10minute'		
            if (self._loginterval_combo.get_active() == 4):
                self.logginginterval_status = '30minute'		

    def _pauseplay_control_cb(self, data=None):
        if self.ag.get_freeze_the_display()==True:
            self.ag.set_freeze_the_display(False)
            self._pause.set_icon('media-playback-pause-insensitive')
            self._pause.set_tooltip(_('Unfreeze the display'))
            self._pause.show()
        else:
            self.ag.set_freeze_the_display(True)
            self._pause.set_icon('media-playback-pause')
            self._pause.set_tooltip(_('Freeze the display'))
            self._pause.show()
        return False

    def _timefreq_control_cb(self, data=None, time_state=True):
        if time_state==True and self.wave.get_fft_mode()==True:
            self.wave.set_fft_mode(False)
            self._time.set_icon('domain-time2')
            self._freq.set_icon('domain-freq')
            self._time.show()
            self._freq.show()
            self._update_string_for_textbox()
            return False
        if time_state==False and self.wave.get_fft_mode()==False:		
            self.wave.set_fft_mode(True)
            self._time.set_icon('domain-time')
            self._freq.set_icon('domain-freq2')
            self._time.show()
            self._freq.show()
            self._update_string_for_textbox()
        return False

    def cb_page_sizef(self, get, data=None):
        if(get.value>=10 and get.value<20):
            self._freq_range.set_value(10)
            self.ag.set_sampling_rate(4000)
            self.wave.set_freq_range(1)
        if(get.value>=20 and get.value<46):
            self._freq_range.set_value(30)
            self.ag.set_sampling_rate(4000)
            self.wave.set_freq_range(2)
        if(get.value>=46 and get.value<62):
            self._freq_range.set_value(50)
            self.ag.set_sampling_rate(16000)
            self.wave.set_freq_range(3)
        if(get.value>=62 and get.value<=70):
            self._freq_range.set_value(70)
            self.ag.set_sampling_rate(48000)
            self.wave.set_freq_range(4)
        self._update_string_for_textbox()
        return True

    def calculate_x_axis_scale(self):	
        sampling_rate = self.ag.get_sampling_rate()
        draw_interval = self.wave.get_drawing_interval()
        if self.wave.get_fft_mode() == False:
            scale = (50000.0/sampling_rate)/draw_interval
            #TODO: fix this [:4] bad bad hack!
            self._STR_SCALEX = self._STR_XAXIS1 + str(scale)[:4] + \
                               self._STR_XAXIS2
            return
        else:
            #TODO: fix this [:4] bad bad hack!
            scale = 1.04167/draw_interval
            self._STR_SCALEX = self._STR_XAXIS1 + str(scale)[:4] + \
                               self._STR_XAXIS3
            return

    def context_off(self):
        """When some other context is switched to and the sound context 
        is switched off"""
        self.g, self.y_mag = self.wave.get_mag_params()
        self.capture_gain = self.ag.get_capture_gain()
        self.mic_boost = self.ag.get_mic_boost()
        self.ag.stop_sound_device()
        self.wave.set_fft_mode(False)

    def context_on(self):
        """When the sound context is switched on"""
        self.ag.start_sound_device()
        self.ag.set_dc_mode(False)
        self.ag.set_bias(True)
        self.ag.set_capture_gain(self.capture_gain)
        self.ag.set_mic_boost(self.mic_boost)
        self.wave.set_fft_mode(False)
        self.wave.set_mag_params(self.g, self.y_mag)
        self._update_string_for_textbox()

    def _update_string_for_textbox(self):
        self.calculate_x_axis_scale()
        self.string_for_textbox = ""
        self.string_for_textbox += (self._STR_BASIC + "\t")
        if self.wave.get_fft_mode() == False:
            self.string_for_textbox += self._STR1
        else:
            self.string_for_textbox += self._STR2
        if self.wave.get_invert_state()==True:
            self.string_for_textbox += self._STR3
        self.string_for_textbox += ("\n" + self._STR_SCALEX)
        self.textbox_copy.set_data_params(0, self.string_for_textbox)

