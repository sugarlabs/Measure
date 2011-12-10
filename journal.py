#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2009,10 Walter Bender
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

import gtk
import cairo

from os import environ, remove
from os.path import join, exists
from numpy import array
from gettext import gettext as _

from sugar.datastore import datastore

# Initialize logging.
import logging
log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)
logging.basicConfig()


class DataLogger():
    """ Handles all of the data I/O with the Journal """

    def __init__(self, activity):
        """ We store csv data in the Journal entry for Measure; screen captures
            are stored in separate Journal entries """
        self.activity = activity
        self.new_session = True
        self.temp_buffer = []
            
    def start_new_session(self, user='', xscale=0, yscale=0,
                          logging_interval='', channels=1):
        """ Start a new logging session by updating session parameters """
        self.activity.session_id += 1

        self.temp_buffer.append("%s: %s" % (_('Session'),
                                            str(self.activity.session_id)))
        self.temp_buffer.append("%s: %s" % (_('User'), user))
        self.temp_buffer.append("%s: %s" % (_('Interval'),
                                            str(logging_interval)))
        self.temp_buffer.append("%s: %d" % (_('Channels'),
                                            channels))

        self.new_session = True
        return self.activity.session_id

    def write_value(self, value=0):
        """Append the value passed to temp_buffer """
        self.temp_buffer.append(value)

    def stop_session(self):
        """Write the temp_buffer onto a file"""
        return
    
    def take_screenshot(self, capture_count=1):
        """ Take a screenshot and save to the Journal """
        tmp_file_path = join(environ['SUGAR_ACTIVITY_ROOT'], 'instance',
                         'screen_capture_' + str(capture_count) + '.png')

        log.debug('saving screen capture to temp file %s' % (tmp_file_path))

        gtk.threads_enter()

        win = self.activity.wave.get_window()
        cr = win.cairo_create()
        surface = cr.get_target()
        width, height =  gtk.gdk.screen_width(), gtk.gdk.screen_height()
        img_surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
        cr = cairo.Context(img_surface)
        cr.set_source_surface(surface)
        cr.paint()
        img_surface.write_to_png(tmp_file_path)

        gtk.threads_leave()
        if exists(tmp_file_path):
            dsobject = datastore.create()
            try:
                dsobject.metadata['title'] = "%s %d" % (_('Waveform'),
                                                       capture_count)
                dsobject.metadata['keep'] = '0'
                dsobject.metadata['buddies'] = ''
                dsobject.metadata['preview'] = ''
                dsobject.metadata['icon-color'] = self.activity.icon_colors
                dsobject.metadata['mime_type'] = 'image/png'
                dsobject.file_path = tmp_file_path
                datastore.write(dsobject)
            finally:
                dsobject.destroy()
                del dsobject
            remove(tmp_file_path)
            return True
        return False
