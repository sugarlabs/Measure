# -*- coding: utf-8 -*-
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
import gtk
from textbox import TextBox
import gobject
import dbus
from os import environ, path, remove
from os.path import join, exists
import csv

from gettext import gettext as _

from sugar.activity import activity
try:  # 0.86+ toolbar widgets
    from sugar.graphics.toolbarbox import ToolbarBox
    _has_toolbarbox = True
except ImportError:
    _has_toolbarbox = False

if _has_toolbarbox:
    from sugar.activity.widgets import ActivityToolbarButton
    from sugar.activity.widgets import StopButton
    from sugar.graphics.toolbarbox import ToolbarButton
    from sugar.graphics.toolbutton import ToolButton
else:
    from sugar.activity.activity import ActivityToolbox

from sugar.datastore import datastore

try:
    from sugar import profile
    _using_gconf = False
except ImportError:
    _using_gconf = True
try:
    import gconf
except ImportError:
    _using_gconf = False

from journal import JournalInteraction
from audiograb import AudioGrab_XO15, AudioGrab_XO1, AudioGrab_Unknown
from drawwaveform import DrawWaveform
from toolbar_side import SideToolbar
from sound_toolbar import SoundToolbar
from sensor_toolbar import SensorToolbar
from config import TOOLBARS, ICONS_DIR, XO1, XO15, UNKNOWN

import logging

log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)
logging.basicConfig()

# Hardware configurations
XO1 = 'xo1'
XO15 = 'xo1.5'
UNKNOWN = 'unknown'


def _is_xo(hw):
    """ Return True if this is xo hardware """
    return hw in [XO1, XO15]


def _get_hardware():
    """ Determine whether we are using XO 1.0, 1.5, or "unknown" hardware """
    product = _get_dmi('product_name')
    if product is None:
        if exists('/etc/olpc-release') or exists('/sys/power/olpc-pm'):
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
    else:
        return UNKNOWN


def _get_dmi(node):
    ''' The desktop management interface should be a reliable source
    for product and version information. '''
    path = join('/sys/class/dmi/id', node)
    try:
        return open(path).readline().strip()
    except:
        return None


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
            tmp_dir = path.join(activity.get_activity_root(), "data")
        except AttributeError:
            # Early versions of Sugar (e.g., 656) didn't support
            # get_activity_root()
            tmp_dir = path.join(environ['HOME'],
                          ".sugar/default/org.laptop.MeasureActivity/data")
        self.using_gconf = _using_gconf
        self.icon_colors = self.get_icon_colors_from_sugar()
        self.stroke_color, self.fill_color = self.icon_colors.split(',')
        self.nick = self.get_nick_from_sugar()
        self.active_status = True
        self.ACTIVE = True
        self.LOGGING_IN_SESSION = False
        self.CONTEXT = ''
        self.adjustmentf = None  # Freq. slider control
        self.connect('notify::active', self._active_cb)
        self.connect('destroy', self.on_quit)
        self.hw = _get_hardware()

        self.session_id = 0

        self.ji = JournalInteraction(self)
        self.wave = DrawWaveform(self)

        self.hw = _get_hardware()
        log.debug('running on %s hardware' % (self.hw))
        if self.hw == XO15:
            self.audiograb = AudioGrab_XO15(self.wave.new_buffer, self)
        elif self.hw == XO1:
            self.audiograb = AudioGrab_XO1(self.wave.new_buffer, self)
        else:
            self.audiograb = AudioGrab_Unknown(self.wave.new_buffer, self)

        # no sharing
        self.max_participants = 1

        self.has_toolbarbox = _has_toolbarbox

        self.side_toolbar = SideToolbar(self)
        self.text_box = TextBox()

        self.box3 = gtk.HBox(False, 0)
        self.box3.pack_start(self.wave, True, True, 0)
        self.box3.pack_start(self.side_toolbar.box1, False, True, 0)

        self.box1 = gtk.VBox(False, 0)
        self.box1.pack_start(self.box3, True, True, 0)
        self.box1.pack_start(self.text_box.box_main, False, True, 0)

        self.set_canvas(self.box1)

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
            toolbox.connect('current-toolbar-changed',
                                 self._toolbar_changed_cb)

        self.sound_toolbar = SoundToolbar(self)
        if self.has_toolbarbox:
            self._sound_button = ToolbarButton(
                label=_('Sound'),
                page=self.sound_toolbar,
                icon_name='media-audio')
            toolbox.toolbar.insert(self._sound_button, -1)
            self._sound_button.show()
        else:
            toolbox.add_toolbar(_('Sound'), self.sound_toolbar)
        self.sound_toolbar.show()

        if _is_xo(self.hw):
            self.sensor_toolbar = SensorToolbar(self)
            if self.has_toolbarbox:
                self._sensor_button = ToolbarButton(
                    label=_('Sensors'),
                    page=self.sensor_toolbar,
                    icon_name='sensor-tools')
                toolbox.toolbar.insert(self._sensor_button, -1)
                self._sensor_button.show()
            else:
                toolbox.add_toolbar(_('Sensors'), self.sensor_toolbar)
            self.sensor_toolbar.show()

        if self.has_toolbarbox:
            _separator = gtk.SeparatorToolItem()
            _separator.props.draw = False
            toolbox.toolbar.insert(_separator, -1)
            _separator.show()

            # add a "dummy" button to indicate what capture mode we are in
            self.label_button = ToolButton('domain-time2')
            toolbox.toolbar.insert(self.label_button, -1)
            self.label_button.show()
            self.label_button.set_tooltip(_('Time Base'))
            self.label_button.connect('clicked', self._label_cb)

            self.sound_toolbar.add_frequency_slider(toolbox.toolbar)

            _separator = gtk.SeparatorToolItem()
            _separator.props.draw = False
            _separator.set_expand(True)
            toolbox.toolbar.insert(_separator, -1)
            _separator.show()
            _stop_button = StopButton(self)
            _stop_button.props.accelerator = _('<Ctrl>Q')
            toolbox.toolbar.insert(_stop_button, -1)
            _stop_button.show()

            self.set_toolbox(toolbox)
            self._sound_button.set_expanded(True)

        else:
            toolbox.set_current_toolbar(TOOLBARS.index('sound'))

        toolbox.show()
        self.sound_toolbar.update_page_size()

        self.show_all()

        self.first = True

        self.set_sound_context()
        self.set_show_hide_windows()
        self.wave.set_active(True)
        self.wave.set_context_on()

    def set_show_hide_windows(self, mode='sound'):
        """Shows the appropriate window identified by the mode """
        if mode == 'sound':
            self.wave.set_context_on()
            self.side_toolbar.set_show_hide(True, mode)
        elif mode == 'sensor':
            self.wave.set_context_on()
            self.side_toolbar.set_show_hide(True, mode)

    def on_quit(self, data=None):
        """Clean up, close journal on quit"""
        self.audiograb.on_activity_quit()

    def _active_cb(self, widget, pspec):
        """ Callback to handle starting/pausing capture when active/idle """
        if self.first:
            self.audiograb.start_grabbing()
            self.first = False
        if not self.props.active and self.ACTIVE:
            self.audiograb.pause_grabbing()
            self.active_status = False
        elif self.props.active and not self.ACTIVE:
            self.audiograb.resume_grabbing()
            self.active_status = True

        self.ACTIVE = self.props.active
        self.wave.set_active(self.ACTIVE)

    def write_file(self, file_path):
        """ Write data to journal on quit """
        if hasattr(self, 'ji') and len(self.ji.temp_buffer) > 0:
            # Append new data to Journal entry
            writer = csv.writer(open(file_path, 'ab'))

            # Also output to a separate file as a workaround to Ticket 2127
            tmp_file_path = join(environ['SUGAR_ACTIVITY_ROOT'], 'instance',
                                 'sensor_data' + '.csv')
            log.debug('saving sensor data to %s' % (tmp_file_path))
            writer2 = csv.writer(open(tmp_file_path, 'ab'))

            for datum in self.ji.temp_buffer:
                writer.writerow( [ datum ] )
                writer2.writerow( [ datum ] )

            # Set the mimetype so that the file can be read by other Activities
            self.metadata['mime_type'] = 'text/csv'

            jobject = datastore.create()
            jobject.metadata['title'] = _('Measure Log')
            jobject.metadata['keep'] = '0'
            jobject.metadata['buddies'] = ''
            jobject.metadata['preview'] = ''
            jobject.metadata['icon-color'] = self.icon_colors
            jobject.metadata['mime_type'] = 'text/csv'
            jobject.file_path = tmp_file_path
            datastore.write(jobject)
            jobject.destroy()
            del jobject
            remove(tmp_file_path)

    def read_file(self, file_path):
        """ Read csv data from journal on start """
        reader = csv.reader(open(file_path, "rb"))
        # Count the number of sessions
        for r in reader:
            if len(r) > 0:
                if r[0] == _('Session'):
                    self.session_id += 1
                elif r[0].find('abiword') != -1:
                    # File has been opened by Write cannot be read by Measure
                    # See Ticket 2127
                    log.error('File was opened by Write: Measure cannot read')
                    return

    def _label_cb(self, data=None):
        """ Ignore the click on the label button """
        return

    def _toolbar_changed_cb(self, toolbox, num):
        """ Callback for changing the primary toolbar (0.84-) """
        if TOOLBARS[num] == 'sound':
            self.set_sound_context()
        elif TOOLBARS[num] == 'sensor':
            self.set_sensor_context()
        return True

    def set_sound_context(self):
        """ Called when sound toolbar is selected or button pushed """
        self.set_show_hide_windows('sound')
        if _is_xo(self.hw):
            self.sensor_toolbar.context_off()
        gobject.timeout_add(500, self.sound_toolbar.context_on)
        self.CONTEXT = 'sound'

    def set_sensor_context(self):
        """ Called when sensor toolbar is selected or button pushed """
        self.set_show_hide_windows('sensor')
        self.sound_toolbar.context_off()
        gobject.timeout_add(500, self.sensor_toolbar.context_on)
        self.CONTEXT = 'sensor'

    def get_icon_colors_from_sugar(self):
        """Returns the icon colors from the Sugar profile"""
        if self.using_gconf:
            client = gconf.client_get_default()
            return client.get_string('/desktop/sugar/user/color')
        else:
            return profile.get_color().to_string()

    def get_nick_from_sugar(self):
        """ Returns nick from Sugar """
        if self.using_gconf:
            client = gconf.client_get_default()
            return client.get_string('/desktop/sugar/user/nick')
        else:
            return profile.get_nick_name()

gtk.gdk.threads_init()
