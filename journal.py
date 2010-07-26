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

from os import environ, remove
from os.path import join
from numpy import array
from gettext import gettext as _

from sugar.datastore import datastore

# Initialize logging.
import logging
log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)
logging.basicConfig()


class JournalInteraction():
    """ Handles all of the data I/O with the Journal """

    def __init__(self, activity):
        """ We store csv data in the Journal entry for Measure; screen captures
            are stored in separate Journal entries """
        self.activity = activity
        self.logginginterval_status = ' '
        self.writer1 = None
        self.writer2 = None
        self.new_session = True
        self.temp_buffer = []
        self._stopped = True
        
        self.jobject = None
   
        self.user = ""
        self.xscale = 0
        self.yscale = 0
    
    def start_new_session(self, user="", xscale=0, yscale=0, \
                          logginginterval_status=' '):
        """ Start a new logging session by updating session parameters """
        self.user = user
        self.xscale = xscale
        self.yscale = yscale
        self.logginginterval_status = logginginterval_status
        self.activity.session_id += 1
        self.new_session = True
        return self.activity.session_id

    def write_value(self, value=0):
        """Append the value passed to temp_buffer """
        self.temp_buffer.append(value)
        self._stopped = False

    def stop_session(self):
        """Write the temp_buffer onto a file"""
        return
        """
        if not self._stopped:
            if self.activity.existing:
                writer1 = csv.writer(open(self.activity._jobject.file_path,
                                          "ab"))
            else:
                writer1 = csv.writer(open(self.activity._jobject.file_path,
                                          "wb"))
                self.activity.existing = True
            for datum in self.temp_buffer:
                writer1.writerow( [ datum ] )
            del writer1
            self.temp_buffer = []
            self.new_session = True
            try:
                self.jobject = datastore.create()
                try:
                    self.jobject.metadata['title'] = "%s %s" %\
                        (_("Measure Log"), str(self.logginginterval_status))
                    self.jobject.metadata['keep'] = '0'
                    self.jobject.metadata['buddies'] = ''
                    self.jobject.metadata['preview'] = ''
                    self.jobject.metadata['icon-color'] = \
                        self.activity.icon_colors
                    self.jobject.metadata['mime_type'] = 'text/csv'
                    self.jobject.file_path = self.activity._jobject.file_path
                    datastore.write(self.jobject)
                finally:
                    pass
            finally:
                log.debug("$$$ in outermost finally!!")
            self._stopped = True
        return False
        """
    
    def write_session_params(self):
        """Write the session parameters to temp_buffers"""
        self.temp_buffer.append("%s: %s" % (_('Session'),
                                            str(self.activity.session_id)))
        self.temp_buffer.append("%s: %s" % (_('User'), str(self.user)))
        self.temp_buffer.append("%s: %s" % (_('Interval'),
                                            str(self.logginginterval_status)))
    
    def take_screenshot(self, waveform_id=1):
        """ Take a screenshot and save to the Journal """
        tmp_file_path = join(environ['SUGAR_ACTIVITY_ROOT'], 'instance',
                         'screen_capture_' + str(waveform_id) + '.png')

        log.debug('saving screen capture to temp file %s' % (tmp_file_path))

        gtk.threads_enter()
        window = gtk.gdk.get_default_root_window()
        width, height = window.get_size()
        x_orig, y_orig = window.get_origin()
        screenshot = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, has_alpha=False,
                                    bits_per_sample=8, width=width,
                                    height=height)
        screenshot.get_from_drawable(window, window.get_colormap(), x_orig,
                                     y_orig, 0, 0, width, height)
        screenshot.save(tmp_file_path, "png")
        gtk.threads_leave()
        try:
            jobject = datastore.create()
            try:
                jobject.metadata['title'] = "%s %d" % (_('Waveform'),
                                                       waveform_id)
                jobject.metadata['keep'] = '0'
                jobject.metadata['buddies'] = ''
                jobject.metadata['preview'] = ''
                jobject.metadata['icon-color'] = self.activity.icon_colors
                jobject.metadata['mime_type'] = 'image/png'
                jobject.file_path = tmp_file_path
                datastore.write(jobject)
            finally:
                jobject.destroy()
                del jobject
        finally:
            remove(tmp_file_path)

        log.debug('cleaning up from screen capture save')
