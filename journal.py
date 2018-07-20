#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2009-12 Walter Bender
#    Copyright (C) 2016, James Cameron [Gtk+ 3.0]
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
#    Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301  USA

from gi.repository import Gdk
import cairo
import time
import os
import StringIO
import dbus
from gettext import gettext as _

from sugar3.datastore import datastore
from sugar3.graphics import style

# Initialize logging.
import logging
log = logging.getLogger('measure-activity')
log.setLevel(logging.DEBUG)


class DataLogger():
    ''' Handles all of the data I/O with the Journal '''

    MODE_LABELS = {
        'sound': _('Sound'),
        'resistance': _('Ohms'),
        'voltage': _('Volts'),
        'frequency': _('Hz')}

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
            _('Date'), time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())))
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

        window = self.activity.wave.get_window()
        width, height = window.get_width(), window.get_height()
        surface = Gdk.Window.create_similar_surface(window,
                                                    cairo.CONTENT_COLOR,
                                                    width, height)
        cr = cairo.Context(surface)
        Gdk.cairo_set_source_window(cr, window, 0, 0)
        cr.paint()
        surface.write_to_png(tmp_file_path)

        if os.path.exists(tmp_file_path):
            dsobject = datastore.create()
            try:
                dsobject.metadata['title'] = '%s %d' % (_('Waveform'),
                                                        capture_count)
                dsobject.metadata['keep'] = '0'
                dsobject.metadata['buddies'] = ''
                dsobject.metadata['preview'] = self._get_preview_data(surface)
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

    def _get_preview_data(self, screenshot_surface):
        screenshot_width = screenshot_surface.get_width()
        screenshot_height = screenshot_surface.get_height()

        preview_width, preview_height = style.zoom(300), style.zoom(225)
        preview_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                             preview_width, preview_height)
        cr = cairo.Context(preview_surface)

        scale_w = preview_width * 1.0 / screenshot_width
        scale_h = preview_height * 1.0 / screenshot_height
        scale = min(scale_w, scale_h)

        translate_x = int((preview_width - (screenshot_width * scale)) / 2)
        translate_y = int((preview_height - (screenshot_height * scale)) / 2)

        cr.translate(translate_x, translate_y)
        cr.scale(scale, scale)

        cr.set_source_rgba(1, 1, 1, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_source_surface(screenshot_surface)
        cr.paint()

        preview_str = StringIO.StringIO()
        preview_surface.write_to_png(preview_str)
        return dbus.ByteArray(preview_str.getvalue())
