# -*- coding: utf-8 -*-
#!/usr/bin/python
#
# Written by Arjun Sarwal <arjun@laptop.org>
# Copyright (C) 2007, Arjun Sarwal
# Copyright (C) 2009-11 Walter Bender
# Copyright (C) 2009, Benjamin Berg, Sebastian Berg
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA


import pygst
pygst.require("0.10")
import gtk
from textbox import TextBox
import os
import csv

from gettext import gettext as _

from sugar.activity import activity
try:  # 0.86+ toolbar widgets
    from sugar.graphics.toolbarbox import ToolbarBox
    _has_toolbarbox = False
except ImportError:
    _has_toolbarbox = False

if _has_toolbarbox:
    from sugar.activity.widgets import ActivityToolbarButton
    from sugar.activity.widgets import StopButton
    from sugar.graphics.toolbarbox import ToolbarButton
else:
    from sugar.activity.activity import ActivityToolbox
from sugar.graphics import style
from sugar.datastore import datastore
from sugar.graphics.toolbutton import ToolButton

try:
    from sugar import profile
    _using_gconf = False
except ImportError:
    _using_gconf = True
try:
    import gconf
except ImportError:
    _using_gconf = False

from journal import DataLogger
from audiograb import AudioGrab_XO175, AudioGrab_XO15, AudioGrab_XO1, \
    AudioGrab_Unknown
from drawwaveform import DrawWaveform
from toolbar_side import SideToolbar
from sensor_toolbar import SensorToolbar
from config import ICONS_DIR, XO1, XO15, XO175, UNKNOWN

import logging

log = logging.getLogger('measure-activity')
log.setLevel(logging.DEBUG)
logging.basicConfig()


def _get_hardware():
    ''' Determine whether we are using XO 1.0, 1.5, or "unknown" hardware '''
    product = _get_dmi('product_name')
    if product is None:
        if '/sys/devices/platform/lis3lv02d/position':
            return XO175
        elif os.path.exists('/etc/olpc-release') or \
             os.path.exists('/sys/power/olpc-pm'):
            return XO1
        else:
            return UNKNOWN
    if product != 'XO':
        return UNKNOWN
    version = _get_dmi('product_version')
    if version == '1':
        return XO1
    elif version == '1.5':
        return XO15
    elif version == '1.75':
        return XO175
    else:
        return UNKNOWN


def _get_dmi(node):
    ''' The desktop management interface should be a reliable source
    for product and version information. '''
    path = os.path.join('/sys/class/dmi/id', node)
    try:
        return open(path).readline().strip()
    except:
        return None


class MeasureActivity(activity.Activity):
    ''' Oscilloscope Sugar activity '''

    def __init__(self, handle):
        ''' Init canvas, toolbars, etc.
        The toolbars are in sensor_toolbar.py and toolbar_side.py
        The audio controls are in audiograb.py
        The rendering happens in drawwaveform.py
        Logging is in journal.py '''

        activity.Activity.__init__(self, handle)

        self.mode_images = {}
        self.mode_images['sound'] = gtk.gdk.pixbuf_new_from_file_at_size(
            os.path.join(ICONS_DIR, 'media-audio.svg'), 45, 45)
        self.mode_images['resistance'] = gtk.gdk.pixbuf_new_from_file_at_size(
            os.path.join(ICONS_DIR, 'resistance.svg'), 45, 45)
        self.mode_images['voltage'] = gtk.gdk.pixbuf_new_from_file_at_size(
            os.path.join(ICONS_DIR, 'voltage.svg'), 45, 45)

        self._using_gconf = _using_gconf
        self.icon_colors = self.get_icon_colors_from_sugar()
        self.stroke_color, self.fill_color = self.icon_colors.split(',')
        self.nick = self.get_nick_from_sugar()
        self.CONTEXT = ''
        self.adjustmentf = None  # Freq. slider control
        self.hw = _get_hardware()
        self.new_recording = False
        self.session_id = 0

        self._active = True
        self._dsobject = None

        self.connect('notify::active', self._active_cb)
        self.connect('destroy', self.on_quit)

        self.data_logger = DataLogger(self)

        self.hw = _get_hardware()
        log.debug('running on %s hardware' % (self.hw))
        if self.hw == XO15:
            self.wave = DrawWaveform(self)
            self.audiograb = AudioGrab_XO15(self.wave.new_buffer, self)
        elif self.hw == XO175:
            self.wave = DrawWaveform(self)
            self.audiograb = AudioGrab_XO175(self.wave.new_buffer, self)
        elif self.hw == XO1:
            self.wave = DrawWaveform(self)
            self.audiograb = AudioGrab_XO1(self.wave.new_buffer, self)
        else:
            self.wave = DrawWaveform(self)
            self.audiograb = AudioGrab_Unknown(self.wave.new_buffer, self)

        # no sharing
        self.max_participants = 1

        self.has_toolbarbox = _has_toolbarbox

        box3 = gtk.HBox(False, 0)
        box3.pack_start(self.wave, True, True, 0)

        # We need an event box in order to set the background color.
        side_eventboxes = []
        self.side_toolbars = []
        for i in range(self.audiograb.channels):
            side_eventboxes.append(gtk.EventBox())
            side_eventboxes[i].modify_bg(
                gtk.STATE_NORMAL, style.COLOR_TOOLBAR_GREY.get_gdk_color())
            self.side_toolbars.append(SideToolbar(self, channel=i))
            side_eventboxes[i].add(self.side_toolbars[i].box1)
            box3.pack_start(side_eventboxes[i], False, True, 0)

        # FIX ME: put text box in an event box to set the background
        # color and change font color to white
        self.text_box = TextBox()

        box1 = gtk.VBox(False, 0)
        box1.pack_start(box3, True, True, 0)
        box1.pack_start(self.text_box.box_main, False, True, 0)

        self.set_canvas(box1)

        if self.has_toolbarbox:
            toolbox = ToolbarBox()

            activity_button = ActivityToolbarButton(self)
            toolbox.toolbar.insert(activity_button, 0)
            activity_button.show()
        else:
            toolbox = ActivityToolbox(self)

            # no sharing
            if hasattr(toolbox, 'share'):
                toolbox.share.hide()
            elif hasattr(toolbox, 'props'):
                toolbox.props.visible = False
            self.set_toolbox(toolbox)

        self.sensor_toolbar = SensorToolbar(self, self.audiograb.channels)
        self.control_toolbar = gtk.Toolbar()
        if self.has_toolbarbox:
            sensor_button = ToolbarButton(
                label=_('Sensors'),
                page=self.sensor_toolbar,
                icon_name='sensor-tools')
            toolbox.toolbar.insert(sensor_button, -1)
            sensor_button.show()
        else:
            toolbox.add_toolbar(_('Sensors'), self.sensor_toolbar)
            toolbox.add_toolbar(_("Controls"), self.control_toolbar)
        self.sensor_toolbar.show()

        if self.has_toolbarbox:
            self.label_mode_img = gtk.Image()
            self.label_mode_img.set_from_pixbuf(self.mode_images['sound'])
            self.label_mode_tool = gtk.ToolItem()
            self.label_mode_tool.add(self.label_mode_img)
            self.label_mode_img.set_tooltip_text(_('Time Base'))
            toolbox.toolbar.insert(self.label_mode_tool, -1)

            separator = gtk.SeparatorToolItem()
            separator.props.draw = True
            toolbox.toolbar.insert(separator, -1)
            separator.show()

            self.sensor_toolbar.add_frequency_slider(toolbox.toolbar)

            separator = gtk.SeparatorToolItem()
            separator.props.draw = True
            toolbox.toolbar.insert(separator, -1)
            separator.show()

            self._pause = ToolButton('media-playback-pause')
            toolbox.toolbar.insert(self._pause, -1)
            self._pause.set_tooltip(_('Capture sample now'))
            self._pause.connect('clicked', self._pause_play_cb)

            separator = gtk.SeparatorToolItem()
            separator.props.draw = False
            separator.set_expand(True)
            toolbox.toolbar.insert(separator, -1)
            separator.show()

            stop_button = StopButton(self)
            stop_button.props.accelerator = _('<Ctrl>Q')
            toolbox.toolbar.insert(stop_button, -1)
            stop_button.show()

            self.set_toolbox(toolbox)
            sensor_button.set_expanded(True)
        else:
            self.sensor_toolbar.add_frequency_slider(self.control_toolbar)

            separator = gtk.SeparatorToolItem()
            separator.props.draw = True
            self.control_toolbar.insert(separator, -1)
            separator.show()

            self._pause = ToolButton('media-playback-pause')
            self.control_toolbar.insert(self._pause, -1)
            self._pause.set_tooltip(_('Capture sample now'))
            self._pause.connect('clicked', self._pause_play_cb)

            toolbox.set_current_toolbar(1)

        toolbox.show()
        self.sensor_toolbar.update_page_size()

        self.show_all()

        self._first = True

        # Always start in 'sound' mode.
        self.sensor_toolbar.set_mode('sound')
        self.sensor_toolbar.set_sound_context()
        self.sensor_toolbar.set_show_hide_windows()
        self.wave.set_active(True)
        self.wave.set_context_on()

    def on_quit(self, data=None):
        '''Clean up, close journal on quit'''
        self.audiograb.on_activity_quit()

    def _active_cb(self, widget, pspec):
        ''' Callback to handle starting/pausing capture when active/idle '''
        if self._first:
            self.audiograb.start_grabbing()
            self._first = False
        if not self.props.active and self._active:
            self.audiograb.pause_grabbing()
        elif self.props.active and not self._active:
            self.audiograb.resume_grabbing()

        self._active = self.props.active
        self.wave.set_active(self._active)

    def write_file(self, file_path):
        ''' Write data to journal, if there is any data to write '''
        if hasattr(self, 'data_logger') and \
                self.new_recording and \
                len(self.data_logger.data_buffer) > 0:
            # Append new data to Journal entry
            fd = open(file_path, 'ab')
            writer = csv.writer(fd)
            # Also output to a separate file as a workaround to Ticket 2127
            # (the assumption being that this file will be opened by the user)
            tmp_data_file = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],
                                 'instance', 'sensor_data' + '.csv')
            log.debug('saving sensor data to %s' % (tmp_data_file))
            if self._dsobject is None:  # first time, so create
                fd2 = open(tmp_data_file, 'wb')
            else:  # we've been here before, so append
                fd2 = open(tmp_data_file, 'ab')
            writer2 = csv.writer(fd2)
            # Pop data off start of buffer until it is empty
            for i in range(len(self.data_logger.data_buffer)):
                datum = self.data_logger.data_buffer.pop(0)
                writer.writerow([datum])
                writer2.writerow([datum])
            fd.close()
            fd2.close()

            # Set the proper mimetype
            self.metadata['mime_type'] = 'text/csv'

            if os.path.exists(tmp_data_file):
                if self._dsobject is None:
                    self._dsobject = datastore.create()
                    self._dsobject.metadata['title'] = _('Measure Log')
                    self._dsobject.metadata['icon-color'] = self.icon_colors
                    self._dsobject.metadata['mime_type'] = 'text/csv'
                self._dsobject.set_file_path(tmp_data_file)
                datastore.write(self._dsobject)
                # remove(tmp_data_file)

    def read_file(self, file_path):
        ''' Read csv data from journal on start '''
        reader = csv.reader(open(file_path, "rb"))
        # Count the number of sessions
        for row in reader:
            if len(row) > 0:
                if row[0].find(_('Session')) != -1:
                    log.debug('found a previously recorded session')
                    self.session_id += 1
                elif row[0].find('abiword') != -1:
                    # File has been opened by Write cannot be read by Measure
                    # See Ticket 2127
                    log.error('File was opened by Write: Measure cannot read')
                    self.data_logger.data_buffer = []
                    return
                self.data_logger.data_buffer.append(row[0])
        if self.session_id == 0:
            log.debug('setting data_logger buffer to []')
            self.data_logger.data_buffer = []

    def _pause_play_cb(self, button=None):
        ''' Callback for Pause Button '''
        if self.audiograb.get_freeze_the_display():
            self.audiograb.set_freeze_the_display(False)
            self._pause.set_icon('media-playback-start')
            self._pause.set_tooltip(_('Unfreeze the display'))
            self._pause.show()
        else:
            self.audiograb.set_freeze_the_display(True)
            self._pause.set_icon('media-playback-pause')
            self._pause.set_tooltip(_('Capture sample now'))
            self._pause.show()
        return False

    def get_icon_colors_from_sugar(self):
        ''' Returns the icon colors from the Sugar profile '''
        if self._using_gconf:
            client = gconf.client_get_default()
            return client.get_string('/desktop/sugar/user/color')
        else:
            return profile.get_color().to_string()

    def get_nick_from_sugar(self):
        ''' Returns nick from Sugar '''
        if self._using_gconf:
            client = gconf.client_get_default()
            return client.get_string('/desktop/sugar/user/nick')
        else:
            return profile.get_nick_name()

gtk.gdk.threads_init()
