#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2009-12 Walter Bender
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
import time
import os
from numpy import array
from gettext import gettext as _

from sugar.datastore import datastore

# Initialize logging.
import logging
log = logging.getLogger('measure-activity')
log.setLevel(logging.DEBUG)
logging.basicConfig()


class DataLogger():
    ''' Handles all of the data I/O with the Journal '''

    MODE_LABELS = {
        'sound': _('Sound'),
        'resistance': _('Ohms'),
        'voltage': _('Volts'),
        'frequency': _('Hz')
        }

    def __init__(self, activity):
        ''' We store csv data in the Journal entry for Measure; screen captures
            are stored in separate Journal entries '''
        self.activity = activity
        self.data_buffer = []

    def start_new_session(self, user='', xscale=0, yscale=0,
                          logging_interval='', channels=1, mode='sound'):
        ''' Start a new logging session by updating session parameters '''
        self.activity.session_id += 1

        self.data_buffer.append('%s: %d' % (_('Session'),
                                            self.activity.session_id))
        self.data_buffer.append('%s: %s' % (_('User'), user))
        self.data_buffer.append('%s: %s' % (_('Mode'), self.MODE_LABELS[mode]))
        self.data_buffer.append('%s: %s' % (
                _('Date'), time.strftime('%Y-%m-%d %H:%M:%S',
                                         time.localtime())))
        self.data_buffer.append('%s: %s' % (_('Interval'),
                                            str(logging_interval)))
        if channels > 1:
            self.data_buffer.append('%s: %d' % (_('Channels'),
                                                channels))
        return self.activity.session_id

    def write_value(self, value='', channel=None, sample=0):
        '''Append the value passed to data_buffer '''
        if channel is None:
            self.data_buffer.append('%d: %s' % (sample, str(value)))
        elif self.activity.wave.visibility[channel]:
            self.data_buffer.append('%d.%d: %s' % (
                    sample, channel, str(value)))

    def stop_session(self):
        '''Write the data_buffer onto a file'''
        return

    def take_screenshot(self, capture_count=1):
        ''' Take a screenshot and save to the Journal '''
        tmp_file_path = os.path.join(
            os.environ['SUGAR_ACTIVITY_ROOT'], 'instance',
            'screen_capture_' + str(capture_count) + '.png')

        log.debug('saving screen capture to temp file %s' % (tmp_file_path))

        gtk.threads_enter()

        win = self.activity.wave.get_window()
        width, height = win.get_size()
        cr = win.cairo_create()
        surface = cr.get_target()
        img_surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
        cr = cairo.Context(img_surface)
        cr.set_source_surface(surface)
        cr.paint()
        img_surface.write_to_png(tmp_file_path)

        gtk.threads_leave()
        if os.path.exists(tmp_file_path):
            dsobject = datastore.create()
            try:
                dsobject.metadata['title'] = '%s %d' % (_('Waveform'),
                                                       capture_count)
                dsobject.metadata['keep'] = '0'
                dsobject.metadata['buddies'] = ''
                dsobject.metadata['preview'] = ''
                dsobject.metadata['icon-color'] = self.activity.icon_colors
                dsobject.metadata['mime_type'] = 'image/png'
                dsobject.set_file_path(tmp_file_path)
                datastore.write(dsobject)
            finally:
                dsobject.destroy()
                del dsobject
            os.remove(tmp_file_path)
            return True
        return False
