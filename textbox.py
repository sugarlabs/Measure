#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2010 Walter Bender
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

class TextBox:
    """ A textbox for displaying status at the bottom of the screen """
    def __init__(self):
        """ Create the textbox """
        self.box_main = gtk.HBox()
        self.text_buffer = gtk.TextBuffer()
        self.text_box = gtk.TextView(self.text_buffer)
        self.box_main.pack_start(self.text_box, True, True, 0)
        self.box_main.show_all()

        self._data_params = []
        self._data_show_state = []
        self._final_string = ""

        self._set_default_data_params()
        self._set_default_data_show_state()

    def _set_default_data_params(self):
        """ By default, time/analog """
        self._data_params.append('Time Scale')

    def _set_default_data_show_state(self):
        self._data_show_state.append(True)

    def write_text(self, text_to_show=''):
        """ Update the textbox """
        self.text_buffer.set_text(text_to_show)

    def refresh_text_box(self):
        self._set_final_string()
        self.write_text(self._final_string)
        return True

    def _set_final_string(self):
        self._final_string = self._data_params[0]

    def set_data_params(self, param_id=0, value=None):
        """
        Updates the parameters to be shown in the textbox
        Param_id    String
        0            string from sensors toolbar
        """
        if param_id == 0:
            self._data_params[0] = value
        self.refresh_text_box()

    def set_data_show_state(self, param_id=0, state=True):
        self._data_show_state[param_id] = state
