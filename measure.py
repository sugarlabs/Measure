#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# Written by Arjun Sarwal <arjun@laptop.org>
# Copyright (C) 2007, Arjun Sarwal
# Copyright (C) 2009-13 Walter Bender
# Copyright (C) 2009, Benjamin Berg, Sebastian Berg
# Copyright (C) 2016, James Cameron [GStreamer 1.0, Gtk+ 3.0]
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA

import gi

vs = {'Gdk': '3.0', 'Gst': '1.0', 'Gtk': '3.0', 'SugarExt': '1.0'}
for api, ver in vs.items():
    gi.require_version(api, ver)

from gi.repository import Gdk, Gtk, GdkPixbuf, Gst, Gio
import os
import csv

from gettext import gettext as _

from sugar3.activity import activity
from sugar3.activity.widgets import ActivityToolbarButton
from sugar3.activity.widgets import StopButton
from sugar3.graphics.alert import Alert
from sugar3.graphics.icon import Icon
from sugar3.graphics.toolbarbox import ToolbarBox
from sugar3.graphics.toolbarbox import ToolbarButton
from sugar3.graphics.toolbutton import ToolButton
from sugar3.graphics import style
from sugar3.datastore import datastore

from sugar3 import profile

from journal import DataLogger
import audiograb
from drawwaveform import DrawWaveform
from toolbar_side import SideToolbar
from sensor_toolbar import SensorToolbar
from tuning_toolbar import TuningToolbar, InstrumentToolbar
from config import ICONS_DIR, INSTRUMENT_DICT

import logging

log = logging.getLogger('measure-activity')
log.setLevel(logging.DEBUG)

PREFIX = '♬'


_OFW_TREE = '/ofw'
_PROC_TREE = '/proc/device-tree'
_DMI_DIRECTORY = '/sys/class/dmi/id'


def _read_file(path):
    if os.access(path, os.R_OK) == 0:
        return None

    fd = open(path, 'r')
    value = fd.read()
    fd.close()
    if value:
        value = value.strip('\n')
        return value
    else:
        return None


def _read_device_tree(path):
    value = _read_file(os.path.join(_PROC_TREE, path))
    if value:
        return value.strip('\x00')
    value = _read_file(os.path.join(_OFW_TREE, path))
    if value:
        return value.strip('\x00')
    return value


def _get_firmware_number():
    firmware_no = _read_device_tree('openprom/model')
    if firmware_no is not None:
        # try to extract Open Firmware version from OLPC style version
        # string, e.g. "CL2   Q4B11  Q4B"
        if firmware_no.startswith('CL'):
            firmware_no = firmware_no[6:13].strip()
        ec_name = _read_device_tree('ec-name')
        if ec_name:
            ec_name = ec_name.replace('Ver:', '')
            firmware_no = '%(firmware)s with %(ec)s' % {
                'firmware': firmware_no, 'ec': ec_name}

    elif os.path.exists(os.path.join(_DMI_DIRECTORY, 'bios_version')):
        firmware_no = _read_file(os.path.join(_DMI_DIRECTORY, 'bios_version'))
    if firmware_no is None:
        firmware_no = _('Not available')
    return firmware_no


def _get_hardware_model():
    settings = Gio.Settings('org.sugarlabs.extensions.aboutcomputer')
    model = settings.get_string('hardware-model')
    if model:
        return model

    model = _read_device_tree('mfg-data/MN')

    if model is None:
        if 'NL3' in _get_firmware_number():
            model = 'NL3'
        if 'VirtualBox' in _get_firmware_number():
            model = 'VirtualBox VM'

    if model is None:
        return 'Unknown'

    return model.split(' ')[0]


class MeasureActivity(activity.Activity):
    ''' Oscilloscope Sugar activity '''

    def __init__(self, handle):
        ''' Init canvas, toolbars, etc.
        The toolbars are in sensor_toolbar.py and toolbar_side.py
        The audio controls are in audiograb.py
        The rendering happens in drawwaveform.py
        Logging is in journal.py '''

        activity.Activity.__init__(self, handle)

        if Gst.version() == (1, 0, 10, 0):
            return self._incompatible()

        self._image_counter = 1

        def mode_image(name):
            path = os.path.join(ICONS_DIR, name)
            return GdkPixbuf.Pixbuf.new_from_file_at_size(path, 45, 45)

        self.mode_images = {}
        self.mode_images['sound'] = mode_image('media-audio.svg')
        self.mode_images['resistance'] = mode_image('resistance.svg')
        self.mode_images['voltage'] = mode_image('voltage.svg')

        self.icon_colors = self.get_icon_colors_from_sugar()
        self.stroke_color, self.fill_color = self.icon_colors.split(',')
        self.nick = self.get_nick_from_sugar()
        self.CONTEXT = ''
        self.adjustmentf = None  # Freq. slider control

        self.hw = _get_hardware_model()

        self.new_recording = False
        self.session_id = 0
        self.read_metadata()

        self._active = True
        self._dsobject = None

        self.connect('notify::active', self._notify_active_cb)
        self.connect('destroy', self.on_quit)

        self.data_logger = DataLogger(self)

        self.wave = DrawWaveform(self)

        ag = audiograb.AudioGrab_Unknown
        ags = {'XO-1': audiograb.AudioGrab_XO1,
               'XO-1.5': audiograb.AudioGrab_XO15,
               'XO-1.75': audiograb.AudioGrab_XO175,
               'XO-4': audiograb.AudioGrab_XO4,
               'NL3': audiograb.AudioGrab_NL3,
               }
        if self.hw in ags:
            ag = ags[self.hw]

        self.audiograb = ag(self.wave.new_buffer, self)

        # no sharing
        self.max_participants = 1

        box3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                       homogeneous=False, spacing=0)
        box3.pack_start(self.wave, True, True, 0)

        # We need event boxes in order to set the background color.
        side_eventboxes = []
        self.side_toolbars = []
        for i in range(self.audiograb.channels):
            side_eventboxes.append(Gtk.EventBox())
            side_eventboxes[i].modify_bg(
                Gtk.StateType.NORMAL, style.COLOR_TOOLBAR_GREY.get_gdk_color())
            self.side_toolbars.append(SideToolbar(self, channel=i))
            side_eventboxes[i].add(self.side_toolbars[i].box1)
            box3.pack_start(side_eventboxes[i], False, True, 0)

        event_box = Gtk.EventBox()
        self.text_box = Gtk.Label()
        self.text_box.set_justify(Gtk.Justification.LEFT)

        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = 1., 1., 1., 1.
        self.text_box.override_background_color(Gtk.StateFlags.NORMAL, rgba)
        event_box.add(self.text_box)
        event_box.modify_bg(
            Gtk.StateType.NORMAL, style.COLOR_TOOLBAR_GREY.get_gdk_color())

        box1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                       homogeneous=False, spacing=0)
        box1.pack_start(box3, True, True, 0)
        box1.pack_start(event_box, False, True, 0)

        self.set_canvas(box1)

        toolbox = ToolbarBox()

        activity_button = ActivityToolbarButton(self)
        toolbox.toolbar.insert(activity_button, 0)
        activity_button.show()

        self.sensor_toolbar = SensorToolbar(self, self.audiograb.channels)
        self.tuning_toolbar = TuningToolbar(self)
        self.new_instrument_toolbar = InstrumentToolbar(self)
        self._extras_toolbar = Gtk.Toolbar()
        self.control_toolbar = Gtk.Toolbar()
        sensor_button = ToolbarButton(
            label=_('Sensors'),
            page=self.sensor_toolbar,
            icon_name='sensor-tools')
        toolbox.toolbar.insert(sensor_button, -1)
        sensor_button.show()
        tuning_button = ToolbarButton(
            # TRANS: Tuning insruments
            label=_('Tuning'),
            page=self.tuning_toolbar,
            icon_name='tuning-tools')
        toolbox.toolbar.insert(tuning_button, -1)
        tuning_button.show()
        new_instrument_button = ToolbarButton(
            label=_('Add instrument'),
            page=self.new_instrument_toolbar,
            icon_name='view-source')
        toolbox.toolbar.insert(new_instrument_button, -1)
        new_instrument_button.show()
        self._extras_button = ToolbarButton(
            page=self._extras_toolbar,
            icon_name='domain-time')
        toolbox.toolbar.insert(self._extras_button, -1)
        self._extras_toolbar_item = Gtk.ToolItem()
        self._extras_toolbar.insert(self._extras_toolbar_item, -1)
        self._extras_button.hide()
        self.sensor_toolbar.show()

        self._extra_tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        # Set up Frequency-domain Button
        self.freq = ToolButton('domain-time')
        self.freq.set_tooltip(_('Time Base'))
        self.freq.connect('clicked', self.timefreq_control)
        self.freq.show()
        self._extra_tools.add(self.freq)

        self.sensor_toolbar.add_frequency_slider(self._extra_tools)

        self._extra_item = Gtk.ToolItem()
        self._extra_item.add(self._extra_tools)
        self._extra_tools.show()
        toolbox.toolbar.insert(self._extra_item, -1)
        self._extra_item.show()

        self._pause = ToolButton('media-playback-pause')
        self._pause.set_tooltip(_('Freeze the display'))
        self._pause.connect('clicked', self._pause_play_cb)
        self._pause.show()
        toolbox.toolbar.insert(self._pause, -1)

        self._capture = ToolButton('image-saveoff')
        self._capture.set_tooltip(_('Capture sample now'))
        self._capture.connect('clicked', self._capture_cb)
        self._capture.show()
        toolbox.toolbar.insert(self._capture, -1)

        separator = Gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        toolbox.toolbar.insert(separator, -1)
        separator.show()

        stop_button = StopButton(self)
        stop_button.props.accelerator = _('<Ctrl>Q')
        toolbox.toolbar.insert(stop_button, -1)
        stop_button.show()

        self.set_toolbar_box(toolbox)
        sensor_button.set_expanded(True)

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

        screen = Gdk.Screen.get_default()
        screen.connect('size-changed', self.__screen_size_changed_cb)
        self.__screen_size_changed_cb(None)

    def __screen_size_changed_cb(self, event):
        ''' Screen size has changed, so check to see if the toolbar
        elements still fit.'''
        self.width = Gdk.Screen.width()
        if self.width < style.GRID_CELL_SIZE * 14:
            self._extras_button.show()
            if self._extra_tools in self._extra_item:
                self._extra_item.remove(self._extra_tools)
            if self._extra_tools not in self._extras_toolbar_item:
                self._extras_toolbar_item.add(self._extra_tools)
            self._extras_toolbar_item.show()
            self.sensor_toolbar.log_label.hide()
            self.sensor_toolbar.trigger_label.hide()
        else:
            self._extras_button.hide()
            if self._extra_tools in self._extras_toolbar_item:
                self._extras_toolbar_item.remove(self._extra_tools)
            if self._extra_tools not in self._extra_item:
                self._extra_item.add(self._extra_tools)
            if self._extras_button.is_expanded():
                self._extras_button.set_expanded(False)
            self._extras_toolbar_item.hide()
            self.sensor_toolbar.log_label.show()
            self.sensor_toolbar.trigger_label.show()
        self._extra_tools.show()

    def on_quit(self, data=None):
        '''Clean up, close journal on quit'''
        self.audiograb.on_activity_quit()

    def _notify_active_cb(self, widget, pspec):
        ''' Callback to handle starting/pausing capture when active/idle '''
        if self._first:
            self.audiograb.start_grabbing()
            self._first = False
        elif not self.props.active:
            self.audiograb.pause_grabbing()
        elif self.props.active:
            self.audiograb.resume_grabbing()

        self._active = self.props.active
        self.wave.set_active(self._active)

    def read_metadata(self):
        ''' Any saved instruments? '''
        for data in list(self.metadata.keys()):
            if data[0] == PREFIX:  # instrument
                log.debug('found an instrument: %s' % (data[1:]))
                instrument = data[1:]
                log.debug(self.metadata[data])
                INSTRUMENT_DICT[instrument] = []
                for note in self.metadata[data].split(' '):
                    INSTRUMENT_DICT[instrument].append(float(note))

    def write_file(self, file_path):
        ''' Write data to journal, if there is any data to write '''
        # Check to see if there are any new instruments to save
        if hasattr(self, 'new_instrument_toolbar'):
            for i, instrument in enumerate(
                    self.new_instrument_toolbar.new_instruments):
                log.debug('saving %s' % (instrument))
                notes = ''
                for i, note in enumerate(INSTRUMENT_DICT[instrument]):
                    notes += '%0.3f' % note
                    if i < len(INSTRUMENT_DICT[instrument]) - 1:
                        notes += ' '
                self.metadata['%s%s' % (PREFIX, instrument)] = notes

        # FIXME: Don't use ""s around data
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
        # Count the number of sessions.
        for row in reader:
            if len(row) > 0:
                if row[0].find(_('Session')) != -1:
                    # log.debug('found a previously recorded session')
                    self.session_id += 1
                elif row[0].find('abiword') != -1:
                    # File has been opened by Write cannot be read by Measure
                    # See Ticket 2127
                    log.error('File was opened by Write: Measure cannot read')
                    self.data_logger.data_buffer = []
                    return
                self.data_logger.data_buffer.append(row[0])
        if self.session_id == 0:
            # log.debug('setting data_logger buffer to []')
            self.data_logger.data_buffer = []

    def _pause_play_cb(self, button=None):
        ''' Callback for Pause Button '''
        if self.audiograb.get_freeze_the_display():
            self.audiograb.set_freeze_the_display(False)
            self._pause.set_icon_name('media-playback-start')
            self._pause.set_tooltip(_('Unfreeze the display'))
            self._pause.show()
        else:
            self.audiograb.set_freeze_the_display(True)
            self._pause.set_icon_name('media-playback-pause')
            self._pause.set_tooltip(_('Freeze the display'))
            self._pause.show()
        return False

    def _capture_cb(self, button=None):
        ''' Callback for screen capture '''
        self.data_logger.take_screenshot(self._image_counter)
        self._image_counter += 1

    def timefreq_control(self, button=None):
        ''' Callback for Freq. Button '''
        # Turn off logging when switching modes
        if self.audiograb.we_are_logging:
            self.sensor_toolbar.record_control_cb()
        if self.wave.get_fft_mode():
            self.wave.set_fft_mode(False)
            self.freq.set_icon_name('domain-time')
            self.freq.set_tooltip(_('Time Base'))
        else:
            self.wave.set_fft_mode(True)
            self.freq.set_icon_name('domain-freq')
            self.freq.set_tooltip(_('Frequency Base'))
            # Turn off triggering in Frequencey Base
            self.sensor_toolbar.trigger_none.set_active(True)
            self.wave.set_trigger(self.wave.TRIGGER_NONE)
            # Turn off invert in Frequencey Base
            for i in range(self.audiograb.channels):
                if self.wave.get_invert_state(channel=i):
                    self.side_toolbars[i].invert_control_cb()
        self.sensor_toolbar.update_string_for_textbox()
        return False

    def get_icon_colors_from_sugar(self):
        ''' Returns the icon colors from the Sugar profile '''
        return profile.get_color().to_string()

    def get_nick_from_sugar(self):
        ''' Returns nick from Sugar '''
        return profile.get_nick_name()

    def _incompatible(self):
        ''' Display abbreviated activity user interface with alert '''
        toolbox = ToolbarBox()
        stop = StopButton(self)
        toolbox.toolbar.add(stop)
        self.set_toolbar_box(toolbox)

        title = _('Activity not compatible with this system.')
        msg = _('Please downgrade activity and try again.')
        alert = Alert(title=title, msg=msg)
        alert.add_button(0, 'Stop', Icon(icon_name='activity-stop'))
        self.add_alert(alert)

        label = Gtk.Label(_('Uh oh, GStreamer is too old.'))
        self.set_canvas(label)

        alert.connect('response', self.__incompatible_response_cb)
        stop.connect('clicked', self.__incompatible_stop_clicked_cb,
                     alert)

        self.show_all()

    def __incompatible_stop_clicked_cb(self, button, alert):
        self.remove_alert(alert)

    def __incompatible_response_cb(self, alert, response):
        self.remove_alert(alert)
        self.close()

Gst.init(None)
