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
import dbus
from time import sleep
from config import TOOLBARS, ICONS_DIR
from tempfile import mkstemp
from os import environ, path, chmod
from textbox import TextBox
from gettext import gettext as _

from sugar.activity import activity
try: # 0.86+ toolbar widgets
    from sugar.bundle.activitybundle import ActivityBundle
    from sugar.activity.widgets import ActivityToolbarButton
    from sugar.activity.widgets import StopButton
    from sugar.graphics.toolbarbox import ToolbarBox
    from sugar.graphics.toolbarbox import ToolbarButton
    _new_sugar_system = True
except ImportError:
    from sugar.activity.activity import ActivityToolbox
    _new_sugar_system = False
from sugar.datastore import datastore

from journal import JournalInteraction
from audiograb import AudioGrab_XO_1_5, AudioGrab_XO_1, AudioGrab_Unknown
from drawwaveform import DrawWaveform
from toolbar_side import SideToolbar
from sound_toolbar import SoundToolbar
from sensor_toolbar import SensorToolbar

try:
    from sugar import profile
    _using_gconf = False
except ImportError:
    _using_gconf = True
try:
    import gconf
except ImportError:
    _using_gconf = False

# Initialize logging.
import logging
log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)
logging.basicConfig()

def _is_xo(hw):
    """ Return True if this is xo hardware """
    return hw in ['xo1','xo1.5']

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
    elif path.exists('/etc/olpc-release') or \
         path.exists('/sys/power/olpc-pm'):
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
            tmp_dir = path.join(activity.get_activity_root(), "data")
        except AttributeError:
            # Early versions of Sugar (e.g., 656) didn't support
            # get_activity_root()
            tmp_dir = path.join(environ['HOME'],
                          ".sugar/default/org.laptop.MeasureActivity/data")
        self.using_gconf = _using_gconf
        self.icon_colors = self.get_icon_colors_from_sugar()
        self.stroke_color, self.fill_color = self.icon_colors.split(",")
        self.nick = self.get_nick_from_sugar()
        self.active_status = True
        self.ACTIVE = True
        self.LOGGING_IN_SESSION = False
        self.CONTEXT = ''
        self.adjustmentf = None # Freq. slider control
        self.connect("notify::active", self._active_cb)
        self.connect("destroy", self.on_quit)	

        if self._jobject.file_path:
            self.existing = True
        else: 
            self._jobject.file_path = str(mkstemp(dir=tmp_dir)[1])
            chmod(self._jobject.file_path, 0777)
            self.existing = False	

        self.ji = JournalInteraction(self)
        self.wave = DrawWaveform(self)
        
        self.hw = _get_hardware()
        log.debug("running on %s hardware" % (self.hw))
        if self.hw == 'xo1.5':
            self.audiograb = AudioGrab_XO_1_5(self.wave.new_buffer, self)
        elif self.hw == 'xo1':
            self.audiograb = AudioGrab_XO_1(self.wave.new_buffer, self)
        else:
            self.audiograb = AudioGrab_Unknown(self.wave.new_buffer, self)

        self.new_sugar_system = _new_sugar_system

        self.side_toolbar = SideToolbar(self)
        self.text_box = TextBox()

        self.box3 = gtk.HBox(False, 0)
        self.box3.pack_start(self.wave, True, True,0)
        self.box3.pack_start(self.side_toolbar.box1, False, True, 0)

        self.box1 = gtk.VBox(False,0)
        self.box1.pack_start(self.box3, True, True, 0)
        self.box1.pack_start(self.text_box.box_main, False, True, 0)

        self.set_canvas(self.box1)		

        if self.new_sugar_system:
            # Use 0.86 toolbar design
            toolbox = ToolbarBox()

            activity_button = ActivityToolbarButton(self)
            toolbox.toolbar.insert(activity_button, 0)
            activity_button.show()
        else:
            toolbox = ActivityToolbox(self)
            self.set_toolbox(toolbox)
            toolbox.connect("current-toolbar-changed",
                                 self._toolbar_changed_cb)

        self.sound_toolbar = SoundToolbar(self)
        if self.new_sugar_system:
            self._sound_button = ToolbarButton(
                label=_('Sound'),
                page=self.sound_toolbar,
                icon_name='sound-tools')
            toolbox.toolbar.insert(self._sound_button, -1)
            self._sound_button.show()
        else:
            toolbox.add_toolbar(_('Sound'), self.sound_toolbar)
        self.sound_toolbar.show()

        if _is_xo(self.hw):
            self.sensor_toolbar = SensorToolbar(self)
            if self.new_sugar_system:
                self._sensor_button = ToolbarButton(
                    label=_('Sensors'),
                    page=self.sensor_toolbar,
                    icon_name='sensor-tools')
                toolbox.toolbar.insert(self._sensor_button, -1)
                self._sensor_button.show()
            else:
                toolbox.add_toolbar(_('Sensors'), self.sensor_toolbar)
            self.sensor_toolbar.show()

        if self.new_sugar_system:
            _separator = gtk.SeparatorToolItem()
            _separator.props.draw = True
            _separator.set_expand(False)
            toolbox.toolbar.insert(_separator, -1)
            _separator.show()
            self.mode_image = gtk.Image()
            self.mode_image.set_from_file(ICONS_DIR + '/domain-time2.svg')
            mode_image_tool = gtk.ToolItem()
            mode_image_tool.add(self.mode_image)
            toolbox.toolbar.insert(mode_image_tool,-1)

            self.label = gtk.Label(" " + _('Time Base'))
            self.label.set_line_wrap(True)
            self.label.show()
            _toolitem = gtk.ToolItem()
            _toolitem.add(self.label)
            toolbox.toolbar.insert(_toolitem, -1)
            _toolitem.show()

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
        return

    def write_file(self, file_path):
        """ Write data to journal on quit """
        return

    def read_file(self, file_path):
        """ Read data from journal on start """
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
        sleep(0.5)
        self.sound_toolbar.context_on()
        self.CONTEXT = 'sound'

    def set_sensor_context(self):
        """ Called when sensor toolbar is selected or button pushed """
        self.set_show_hide_windows('sensor')
        self.sound_toolbar.context_off()
        sleep(0.5)
        self.sensor_toolbar.context_on()
        self.CONTEXT = 'sensor'

    def get_icon_colors_from_sugar(self):
        """Returns the icon colors from the Sugar profile"""
        if self.using_gconf:
            client = gconf.client_get_default()
            return client.get_string("/desktop/sugar/user/color")
        else:
            return profile.get_color().to_string()

    def get_nick_from_sugar(self):
        """ Returns nick from Sugar """
        if self.using_gconf:
            client = gconf.client_get_default()
            return client.get_string("/desktop/suagr/user/nick")
        else:
            return profile.get_nick_name()

gtk.gdk.threads_init()
