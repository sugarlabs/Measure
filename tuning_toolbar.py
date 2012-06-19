# -*- coding: utf-8 -*-
#! /usr/bin/python
#
# Copyright (C) 2009-12 Walter Bender
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA


import gtk
import gobject
import os
from gettext import gettext as _

from config import ICONS_DIR, CAPTURE_GAIN, MIC_BOOST, XO1, XO15, XO175, XO30

from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.combobox import ComboBox
from sugar.graphics.toolcombobox import ToolComboBox
import logging
log = logging.getLogger('measure-activity')
log.setLevel(logging.DEBUG)


class TuningToolbar(gtk.Toolbar):
    ''' The toolbar for tuning instruments '''

    def __init__(self, activity):
        gtk.Toolbar.__init__(self)

        self.activity = activity
        self._show_tuning_line = False

        # Set up Tuning Combo box
        self._tuning_combo = ComboBox()
        self.tuning = [_('None'), _('Guitar'), _('Violin'), _('Viola'),
                       _('Cello'), _('Bass'), _('Charango')]
        self._tuning_changed_id = self._tuning_combo.connect(
            'changed', self.update_tuning_control)
        for i, s in enumerate(self.tuning):
            self._tuning_combo.append_item(i, s, None)
        self._tuning_combo.set_active(0)
        if hasattr(self._tuning_combo, 'set_tooltip_text'):
            self._tuning_combo.set_tooltip_text(_('Tune an instrument.'))
        self._tuning_tool = ToolComboBox(self._tuning_combo)
        self.insert(self._tuning_tool, -1)

        if self.activity.has_toolbarbox:
            separator = gtk.SeparatorToolItem()
            separator.props.draw = True
            self.insert(separator, -1)

        self._freq_entry = gtk.Entry()
        self._freq_entry.set_text('0')
        if hasattr(self._freq_entry, 'set_tooltip_text'):
            self._freq_entry.set_tooltip_text(
                _('Enter a frequency to display.'))
        self._freq_entry.set_width_chars(8)
        self._freq_entry.show()
        toolitem = gtk.ToolItem()
        toolitem.add(self._freq_entry)
        self.insert(toolitem, -1)
        toolitem.show()

        self._new_tuning_line = ToolButton('tuning-tools')
        self._new_tuning_line.show()
        self.insert(self._new_tuning_line, -1)
        self._new_tuning_line.set_tooltip(_('Show tuning line.'))
        self._new_tuning_line.connect('clicked', self.tuning_line_cb)

        if self.activity.has_toolbarbox:
            separator = gtk.SeparatorToolItem()
            separator.props.draw = True
            self.insert(separator, -1)

        self._harmonic = ToolButton('harmonics')
        self._harmonic.show()
        self.insert(self._harmonic, -1)
        self._harmonic.set_tooltip(_('Show harmonics.'))
        self._harmonic.connect('clicked', self.harmonic_cb)

        self.show_all()

    def update_tuning_control(self, *args):
        ''' Callback for tuning control '''
        self.activity.wave.instrument = \
            self.tuning[self._tuning_combo.get_active()]

    def harmonic_cb(self, *args):
        ''' Callback for harmonics control '''
        self.activity.wave.harmonics = not self.activity.wave.harmonics
        if self.activity.wave.harmonics:
            self._harmonic.set_icon('harmonics-off')
            self._harmonic.set_tooltip(_('Hide harmonics.'))
        else:
            self._harmonic.set_icon('harmonics')
            self._harmonic.set_tooltip(_('Show harmonics.'))

    def tuning_line_cb(self, *args):
        ''' Callback for tuning insert '''
        if self._show_tuning_line:
            self.activity.wave.tuning_line = 0.0
            self._new_tuning_line.set_icon('tuning-tools')
            self._new_tuning_line.set_tooltip(_('Show tuning line.'))
            self._show_tuning_line = False
        else:
            freq = self._freq_entry.get_text()
            try:
                self.activity.wave.tuning_line = float(freq)
                self._new_tuning_line.set_icon('tuning-tools-off')
                self._new_tuning_line.set_tooltip(_('Hide tuning line.'))
                self._show_tuning_line = True
            except ValueError:
                self.activity.wave.tuning_line = 0.0
                self._freq_entry.set_text('0')
