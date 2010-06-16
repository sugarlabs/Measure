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
from gettext import gettext as _

def _is_xo(hw):
    """ Return True if this is xo hardware """
    return hw in ['xo1','xo1.5']:

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

        self.connect("current-toolbar-changed", self._toolbar_changed_cb)
        self.wave = activity.wave
        self.activity = activity
        self.set_current_toolbar(config.TOOLBARS.index('sound'))
        return

    def _toolbar_changed_cb(self, tbox, num):
        """ Callback for changing the primary toolbar  """
        if config.TOOLBAR[num] == 'sound':
            self.activity.set_show_hide_windows(config.TOOLBAR[num])
            if _is_xo(self.activity.hw):
                self._sensors_toolbar.context_off()
            time.sleep(0.5)
            self._sound_toolbar.context_on()
        elif config.TOOLBAR[num] == 'sensor':
            self.activity.set_show_hide_windows(config.TOOLBAR[num])
            self._sound_toolbar.context_off()
            time.sleep(0.5)
            self._sensors_toolbar.context_on()

        config.CONTEXT = TOOLBAR[num]
        return True

