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

        # Set up Tuning Combo box
        self._tuning_combo = ComboBox()
        self.tuning = [_('None'), _('Guitar'), _('Violin'), _('Viola'),
                       _('Cello'), _('Bass')]
        self._tuning_changed_id = self._tuning_combo.connect(
            'changed', self.update_tuning_control)
        for i, s in enumerate(self.tuning):
            self._tuning_combo.append_item(i, s, None)
        self._tuning_combo.set_active(0)
        if hasattr(self._tuning_combo, 'set_tooltip_text'):
            self._tuning_combo.set_tooltip_text(_('Tune an instrument'))
        self._tuning_tool = ToolComboBox(self._tuning_combo)
        self.insert(self._tuning_tool, -1)

        self.show_all()

    def update_tuning_control(self, *args):
        ''' Callback for tuning control '''
        self.activity.wave.instrument = \
            self.tuning[self._tuning_combo.get_active()]
