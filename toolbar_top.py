#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, OLPC
#    
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

import config

from sugar.activity.activity import ActivityToolbox

from sound_toolbar import SoundToolbar
from sensor_toolbar import SensorToolbar
from logging_ui import LogToolbar
from gettext import gettext as _

class Toolbar(ActivityToolbox):

    def __init__(self, activity, wave, audiograb, journal, textbox):

        ActivityToolbox.__init__(self, activity)

        self._SOUND_TOOLBAR = 1
        self._SENSOR_TOOLBAR = 2

        self._sound_toolbar = SoundToolbar(wave, audiograb, textbox, journal, activity)
        self.add_toolbar(_('Sound'), self._sound_toolbar)
        self._sound_toolbar.show()

        self._sensors_toolbar = SensorToolbar(wave, audiograb, textbox, journal)
        self.add_toolbar(_('Sensors'), self._sensors_toolbar)
        self._sensors_toolbar.show()

        """
        self._camera_toolbar = CameraToolbar(activity, camera_ui)
        self.add_toolbar('Camera', self._camera_toolbar)
        self._camera_toolbar.show()

        self._wifi_toolbar = MeasureToolbar(wave, audiograb)
        self.add_toolbar('Wireless', self._wifi_toolbar)
        self._wifi_toolbar.show()

        self._log_toolbar = LogToolbar(audiograb, journal, activity)
        self.add_toolbar('Log View', self._log_toolbar)
        self._log_toolbar.show()
        """

        self.connect("current-toolbar-changed", self._toolbar_changed_cb)
        self.wave = wave
        self.activity = activity
        self.toolbar_active_id = 1
        self.set_current_toolbar(self._SOUND_TOOLBAR)


    def _toolbar_changed_cb(self, tbox, num):
        if num==0:                              #Activity
	        pass

        elif num==self._SOUND_TOOLBAR:                           #Sound
            self.activity.set_show_hide_windows(self._SOUND_TOOLBAR)
            self._sensors_toolbar.context_off()
            time.sleep(0.5)
            self._sound_toolbar.context_on()
            config.CONTEXT = self._SOUND_TOOLBAR

        elif num==self._SENSOR_TOOLBAR:                            #Sensor
            self._sound_toolbar.context_off()
            time.sleep(0.5)
            self._sensors_toolbar.context_on()
            self.activity.set_show_hide_windows(self._SENSOR_TOOLBAR)
            config.CONTEXT = self._SENSOR_TOOLBAR

        self.toolbar_active_id = num
        """
        elif num==3:                            #Camera
	        self.activity.set_show_hide_windows(1)
	        self._sound_toolbar.context_off()
	        self.wave.set_context_off()
	        time.sleep(0.5)
	        self._camera_toolbar.set_context_on()
        elif num==4:        
	        self.wave.set_context_off()
	        self._sound_toolbar.context_off()
	        self._camera_toolbar.set_context_off()
	        time.sleep(0.5)
        elif num==5:
	        self.wave.set_context_off() 
	        self._sound_toolbar.context_off()
	        self._camera_toolbar.set_context_off()
	        time.sleep(0.5)
        """
        return True


    def get_which_toolbar_active(self):
        """Returns which toolbar is active
        Activity toolbar - 1
        Sound toolbar 	 - 2
        Sensors toolbar  - 3
        """
        return self.toolbar_active_id



