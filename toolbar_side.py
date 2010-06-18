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

import pygtk
import gtk
from gettext import gettext as _

from sugar.graphics.toolbutton import ToolButton

import config

#class SideToolbar(gtk.DrawingArea):
class SideToolbar(gtk.Toolbar):
    """ A toolbar on the side of the canvas for adjusting gain/bias """

    def __init__(self, activity):
        """ Set up initial toolbars """
        # gtk.DrawingArea.__init__(self)
        gtk.Toolbar.__init__(self)

        self.wave = activity.wave
        self.ag = activity.audiograb
        self.show_toolbar = True

        self.mode = config.CONTEXT
        self.mode_values = {'sound':3, 'sensor':2}

        self.button_up = ToolButton('amp-high')
        self.button_up.set_tooltip(_('Increase amplitude'))
        self.button_up.connect('clicked', self._button_up_cb)
        self.button_up.show()

        self.adjustmenty = gtk.Adjustment(self.mode_values[self.mode], 0.0,
                                          4.0, 0.1, 0.1, 0.0)
        self.adjustmenty.connect("value_changed", self._yscrollbar_cb,
	        self.adjustmenty)
        self.yscrollbar = gtk.VScale(self.adjustmenty)
        self.yscrollbar.set_draw_value(False)
        self.yscrollbar.set_inverted(True)
        self.yscrollbar.set_update_policy(gtk.UPDATE_CONTINUOUS)
		
        self.button_down = ToolButton('amp-low')
        self.button_down.set_tooltip(_('Decrease amplitude'))
        self.button_down.connect('clicked', self._button_down_cb)
        self.button_down.show()

        self.box1 = gtk.VBox(False,0)
        self.box1.pack_start(self.button_up, False, True, 0)
        self.box1.pack_start(self.yscrollbar, True, True, 0)
        self.box1.pack_start(self.button_down, False, True, 0)

        self.set_show_hide(False)

    def _yscrollbar_cb(self, adjy, data=None):
        """ Callback for scrollbar """
        if self.mode == 'sound':
            if adjy.value <= 1.5:	
                self.wave.set_mag_params(1.0, adjy.value)        #0dB
                self.ag.set_capture_gain(0)
            elif adjy.value <= 2.5:
                self.wave.set_mag_params(1.9952, adjy.value*1.5) #6dB
                self.ag.set_capture_gain(25)
            elif adjy.value <= 3.5:
                self.wave.set_mag_params(3.981, adjy.value*3.0) #12dB
                self.ag.set_capture_gain(50)
            else:
                self.wave.set_mag_params(13.335, adjy.value*4.0) #22.5dB
                self.ag.set_capture_gain(100)
            self.wave.set_bias_param(0)
        elif self.mode == 'sensor':
            self.wave.set_bias_param(int((adjy.value-2)*300))
        self.mode_values[self.mode] = adjy.value
        return True

    def _button_up_cb(self, data=None):
        """Moves slider up"""
	new_value = self.yscrollbar.get_value() +\
                    (self.adjustmenty.get_upper() -\
                     self.adjustmenty.get_lower())/100.0
	if new_value <= self.adjustmenty.get_upper():
	    self.yscrollbar.set_value(new_value)
	else:
	    self.yscrollbar.set_value(self.adjustmenty.get_upper())
        return True

    def _button_down_cb(self, data=None):
        """Moves slider down"""
	new_value = self.yscrollbar.get_value() -\
                    (self.adjustmenty.get_upper() -\
                     self.adjustmenty.get_lower())/100.0
	if new_value >= self.adjustmenty.get_lower():
	    self.yscrollbar.set_value(new_value)
	else:
	    self.yscrollbar.set_value(self.adjustmenty.get_lower())
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
