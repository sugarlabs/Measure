# -*- coding: utf-8 -*-
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
from gettext import gettext as _

from sugar.graphics.toolbutton import ToolButton


class SideToolbar(gtk.Toolbar):
    """ A toolbar on the side of the canvas for adjusting gain/bias """

    LOWER = 0.0
    UPPER = 4.0

    def __init__(self, activity):
        """ Set up initial toolbars """
        gtk.Toolbar.__init__(self)

        self.activity = activity
        self.show_toolbar = True

        self.mode = 'sound'
        self.mode_values = {'sound': 3, 'sensor': 2}

        self.button_up = ToolButton('amp-high')
        self.button_up.set_tooltip(_('Increase amplitude'))
        self.button_up.connect('clicked', self._button_up_cb)
        self.button_up.show()

        self.adjustmenty = gtk.Adjustment(self.mode_values[self.mode],
                                          self.LOWER, self.UPPER,
                                          0.1, 0.1, 0.0)
        self.adjustmenty.connect('value_changed', self._yscrollbar_cb,
                                 self.adjustmenty)
        self.yscrollbar = gtk.VScale(self.adjustmenty)
        self.yscrollbar.set_draw_value(False)
        self.yscrollbar.set_inverted(True)
        self.yscrollbar.set_update_policy(gtk.UPDATE_CONTINUOUS)

        self.button_down = ToolButton('amp-low')
        self.button_down.set_tooltip(_('Decrease amplitude'))
        self.button_down.connect('clicked', self._button_down_cb)
        self.button_down.show()

        self.box1 = gtk.VBox(False, 0)
        self.box1.pack_start(self.button_up, False, True, 0)
        self.box1.pack_start(self.yscrollbar, True, True, 0)
        self.box1.pack_start(self.button_down, False, True, 0)

        self.set_show_hide(False)

    def _yscrollbar_cb(self, adjy, data=None):
        """ Callback for scrollbar """
        if self.mode == 'sound':
            print "toolbar side: setting mag to 1.0, %f" % (adjy.value)
            self.activity.wave.set_mag_params(1.0, adjy.value)
            print "toolbar side: setting capture gain to %f" %\
                (adjy.value * 100 / (self.UPPER - self.LOWER))
            self.activity.audiograb.set_capture_gain(
                adjy.value * 100 / (self.UPPER - self.LOWER))
            self.activity.wave.set_bias_param(0)
        elif self.mode == 'sensor':
            print "toolbar side: setting bias param to %f" %\
                (300 * (adjy.value - (self.UPPER - self.LOWER) / 2))
            self.activity.wave.set_bias_param(int(
                    300 * (adjy.value - (self.UPPER - self.LOWER) / 2)))
        self.mode_values[self.mode] = adjy.value
        return True

    def _button_up_cb(self, data=None):
        """Moves slider up"""
        new_value = self.yscrollbar.get_value() + (self.UPPER - self.LOWER)\
            / 100.0
        if new_value <= self.UPPER:
            self.yscrollbar.set_value(new_value)
        else:
            self.yscrollbar.set_value(self.UPPER)
        return True

    def _button_down_cb(self, data=None):
        """Moves slider down"""
        new_value = self.yscrollbar.get_value() - (self.UPPER - self.LOWER)\
            / 100.0
        if new_value >= self.LOWER:
            self.yscrollbar.set_value(new_value)
        else:
            self.yscrollbar.set_value(self.LOWER)
        return True

    def set_show_hide(self, show=True, mode='sound'):
        """ Show or hide the toolbar """
        self.show_toolbar = show
        self.set_mode(mode)

    def set_mode(self, mode='sound'):
        """ Set the toolbar to either 'sound' or 'sensor' """
        self.mode = mode
        if self.mode == 'sound':
            self.button_up.set_icon('amp-high')
            self.button_up.set_tooltip(_('Increase amplitude'))
            self.button_down.set_icon('amp-low')
            self.button_down.set_tooltip(_('Decrease amplitude'))
        elif self.mode == 'sensor':
            self.button_up.set_icon('bias-high')
            self.button_up.set_tooltip(_('Increase bias'))
            self.button_down.set_icon('bias-low')
            self.button_down.set_tooltip(_('Decrease bias'))
        self.yscrollbar.set_value(self.mode_values[self.mode])
        return
