#!/usr/bin/python
#
#    Copyright (C) 2007, OLPC
#    Written by Arjun Sarwal <arjun@laptop.org>
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
import config 		#This has all the globals
import os, sys
import tempfile
from os import environ
from os.path import join

from journal import JournalInteraction
from audiograb import AudioGrab
from drawwaveform import DrawWaveform
from toolbar_side import SideToolbar
from toolbar_top import Toolbar
from textbox import TextBox

import logging
from sugar.activity import activity
from sugar.datastore import datastore


class MeasureActivity(activity.Activity):

    def __init__(self, handle):

        activity.Activity.__init__(self, handle)
        act_root = environ['SUGAR_ACTIVITY_ROOT'] 
        tmp_dir = join(act_root, 'data')	   


        self.active_status = True
        self.ACTIVE = True
        self.connect( "notify::active", self._activeCb )
        self.connect("destroy", self.on_quit)	

        if self._jobject.file_path:
	        #logging.debug('1.0 Launched from journal')
	        self.existing = True
        else: 
	        #logging.debug('1.1 Launched from frame or from Mesh View')
	        self._jobject.file_path =str(tempfile.mkstemp(dir=tmp_dir)[1]) 
	        os.chmod(self._jobject.file_path, 0777)
	        self.existing = False	


        self.ji = JournalInteraction(self._jobject.file_path, self.existing)
        self.wave = DrawWaveform()
        self.audiograb = AudioGrab(self.wave.new_buffer, self.ji)
        self.side_toolbar = SideToolbar(self.wave)
        self.text_box = TextBox()


        self.box3 = gtk.HBox(False, 0)
        self.box3.pack_start(self.wave,True,True,0)
        self.box3.pack_start(self.side_toolbar.box1,False,True,0)	

        self.box1 = gtk.VBox(False,0)
        self.box1.pack_start(self.box3, True, True, 0)
        self.box1.pack_start(self.text_box.box_main, False, True, 0)

        self.set_canvas(self.box1)		

        toolbox = Toolbar(self, self.wave, self.audiograb, self.ji, self.text_box)
        self.set_toolbox(toolbox)
        toolbox.show()

        self.show_all()		

        self.first = True

        gobject.timeout_add(config.REFRESH_TIME, self.waveform_refresh)



    def set_show_hide_windows(self, window_id=1):
        """Shows the appropriate window identified by the window_id
        1 --> sound
        2 --> sensors
        """
        if window_id==1: 
            #self.box3.pack_start(self.wave,True,True,0)
            #self.box3.pack_start(self.side_toolbar.box1,False,True,0)	
            #self.box3.show_all()
            self.wave.set_context_on()
            self.side_toolbar.box1.show_all()
            self.active_context_status = 1
            return
	
        elif window_id==2:
            #self.box3.pack_start(self.wave,True,True,0)
            #self.box3.show_all()
            self.wave.set_context_on()
            self.side_toolbar.box1.hide_all()
            self.active_context_status = 2
            return
	

    def get_show_hide_windows(self):
        """Gets which window is being shown
        If 0 is returned means waveform window is being shown
        If 1 is returned means camera context"""
        return self.active_context_status



    def waveform_refresh(self):
        self.wave.queue_draw()
        return self.active_status 						


    def on_quit(self,data=None):	
        self.audiograb.on_activity_quit()	
        self.ji.on_quit()

    def _activeCb( self, widget, pspec ):
        if(self.first == True):
	        self.audiograb.start_grabbing()
	        self.first = False
        if (not self.props.active and self.ACTIVE):
	        self.audiograb.pause_grabbing()
	        self.active_status = False 
        elif (self.props.active and not self.ACTIVE):
	        self.audiograb.resume_grabbing()
	        self.active_status = True                
	        gobject.timeout_add(config.REFRESH_TIME, \
		        self.waveform_refresh)        
        self.ACTIVE = self.props.active


    def write_file(self, file_path):
        self.metadata['fulltext'] = 'blah blah'

    def read_file(self, file_path):
        pass


gtk.gdk.threads_init()



