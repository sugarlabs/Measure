#!/usr/bin/python
#
#    Written by Arjun Sarwal <arjun@laptop.org>
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


import pygst
pygst.require("0.10")
import pygtk
import gtk
import gobject
import time
import dbus
import config 		#This has all the globals
import os
import tempfile
from os import environ
from os.path import join

from journal import JournalInteraction
import audiograb
from drawwaveform import DrawWaveform
from toolbar_side import SideToolbar
from toolbar_top import Toolbar
from textbox import TextBox

from sugar.activity import activity
from sugar.datastore import datastore

# Initialize logging.
import logging
log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)
logging.basicConfig()

def _get_hardware():
    """ Determine whether we are using XO 1.0, 1.5, or "unknown" hardware """
    bus = dbus.SystemBus()
 
    comp_obj = bus.get_object('org.freedesktop.Hal',
                              '/org/freedesktop/Hal/devices/computer')
    dev = dbus.Interface (comp_obj, 'org.freedesktop.Hal.Device')
    if dev.PropertyExists('system.hardware.vendor') and \
            dev.PropertyExists('system.hardware.version'):
        if dev.GetProperty ('system.hardware.vendor') == 'OLPC':
            if dev.GetProperty('system.hardware.version') == '1.5':
                return 'xo1.5'
            else:
                return 'xo1'
        else:
            return 'unknown'
    elif os.path.exists('/etc/olpc-release') or \
         os.path.exists('/sys/power/olpc-pm'):
        return 'xo1'
    # elif 'olpc' in dev.GetProperty('system.kernel.version'):
    #     return 'xo1'
    else:
        return 'unknown'

class MeasureActivity(activity.Activity):
    """ Oscilloscope Sugar activity """

    def __init__(self, handle):
        """ Init canvas, toolbars, etc.
        The toolbars are in toolbar_top.py and toolbar_side.py
        The audio controls are in audiograb.py
        The rendering happens in drawwaveform.py
        Logging (Journal interactions) are in journal.py """

        activity.Activity.__init__(self, handle)

        try:
            tmp_dir = os.path.join(activity.get_activity_root(), "data")
        except:
            # Early versions of Sugar (e.g., 656) didn't support
            # get_activity_root()
            tmp_dir = os.path.join(os.environ['HOME'],
                          ".sugar/default/org.laptop.MeasureActivity/data")

        self.active_status = True
        self.ACTIVE = True
        self.connect("notify::active", self._active_cb)
        self.connect("destroy", self.on_quit)	

        if self._jobject.file_path:
	        #logging.debug('1.0 Launched from journal')
	        self.existing = True
        else: 
	        #logging.debug('1.1 Launched from frame or from Mesh View')
	        self._jobject.file_path = str(tempfile.mkstemp(dir=tmp_dir)[1])
	        os.chmod(self._jobject.file_path, 0777)
	        self.existing = False	

        self.ji = JournalInteraction(self._jobject.file_path, self.existing)
        self.wave = DrawWaveform()
        
        self.hw = _get_hardware()
        print "running on %s hardware" % (self.hw)
        if self.hw == 'xo1.5':
            self.audiograb = \
                audiograb.AudioGrab_XO_1_5(self.wave.new_buffer, self.ji)
        elif self.hw == 'xo1':
            self.audiograb = \
                audiograb.AudioGrab_XO_1(self.wave.new_buffer, self.ji)
        else: # Use 1.5 settings as default, 0)
            self.audiograb = \
                audiograb.AudioGrab_Unknown(self.wave.new_buffer, self.ji)
            # log.error('Sorry, we do not support your hardware yet.')

        self.side_toolbar = SideToolbar(self)
        self.text_box = TextBox()

        self.box3 = gtk.HBox(False, 0)
        self.box3.pack_start(self.wave, True, True,0)
        self.box3.pack_start(self.side_toolbar.box1, False, True, 0)

        self.box1 = gtk.VBox(False,0)
        self.box1.pack_start(self.box3, True, True, 0)
        self.box1.pack_start(self.text_box.box_main, False, True, 0)

        self.set_canvas(self.box1)		

        toolbox = Toolbar(self)
        self.set_toolbox(toolbox)
        toolbox.show()

        self.show_all()		

        self.first = True

        self.set_show_hide_windows()
        self.wave.set_active(True)
        self.wave.set_context_on()

    def set_show_hide_windows(self, mode='sound'):
        """Shows the appropriate window identified by the mode """
        if mode == 'sound': 
            self.wave.set_context_on()
            self.side_toolbar.set_show_hide(True, mode)
            return
        elif mode == 'sensor':
            self.wave.set_context_on()
            self.side_toolbar.set_show_hide(True, mode)
            return

    def on_quit(self,data=None):
        """Clean up, close journal on quit"""
        self.audiograb.on_activity_quit()	
        self.ji.on_quit()
        return

    def _active_cb( self, widget, pspec ):
        """ Callback to handle starting/pausing capture when active/idle """
        if(self.first == True):
	        self.audiograb.start_grabbing()
	        self.first = False
        if (not self.props.active and self.ACTIVE):
	        self.audiograb.pause_grabbing()
	        self.active_status = False 
        elif (self.props.active and not self.ACTIVE):
	        self.audiograb.resume_grabbing()
	        self.active_status = True

        self.ACTIVE = self.props.active
        self.wave.set_active(self.ACTIVE)
        return

    def write_file(self, file_path):
        """ Write data to journal on quit """
        return

    def read_file(self, file_path):
        """ Read data from journal on start """
        return

gtk.gdk.threads_init()
