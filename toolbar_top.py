#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2009, Walter Bender
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
# from logging_ui import LogToolbar
from gettext import gettext as _

def _is_xo(hw):
    """ Return True if this is xo hardware """
    if hw == 'xo1' or hw == 'xo1.5':
        return True
    return False

class Toolbar(ActivityToolbox):

    def __init__(self, activity):

        ActivityToolbox.__init__(self, activity)

        self._sound_toolbar = SoundToolbar(activity)
        self.add_toolbar(_('Sound'), self._sound_toolbar)
        self._sound_toolbar.show()

        if _is_xo(activity.hw):
            self._sensors_toolbar = SensorToolbar(activity)
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
        self.wave = activity.wave
        self.activity = activity
        self.toolbar_active_id = 1
        self.set_current_toolbar('sound')


    def _toolbar_changed_cb(self, tbox, num):
        """ Callback for changing the primary toolbar  """
        if config.TOOLBAR[num]=='sound':
            self.activity.set_show_hide_windows(config.TOOLBAR[num])
            if _is_xo(self.activity.hw):
                self._sensors_toolbar.context_off()
            time.sleep(0.5)
            self._sound_toolbar.context_on()
        elif config.TOOLBAR[num]=='sensor':
            self.activity.set_show_hide_windows(config.TOOLBAR[num])
            self._sound_toolbar.context_off()
            time.sleep(0.5)
            self._sensors_toolbar.context_on()

        config.CONTEXT = TOOLBAR[num]
        self.toolbar_active_id = num
        """
        # for when we implement other sensors
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



