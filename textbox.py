import gtk
import pygtk
from gettext import gettext as _
import gobject

import config  	#This has all the globals

from sugar.graphics.toolbutton import ToolButton

# Textbox class
class TextBox:

	def __init__(self):
		self.box_main = gtk.HBox()
		self.text_buffer = gtk.TextBuffer()
		self.text_box = gtk.TextView(self.text_buffer)
		self.box_main.pack_start(self.text_box, True, True, 0)
		self.box_main.show_all()
		#gobject.timeout_add(300, self.refresh_text_box)

		self._data_params = []
		self._data_show_state = []
		
		self._set_default_data_params()
		self._set_default_data_show_state()


	def _set_default_data_params(self):
		self._data_params.append('Time Scale')


	def _set_default_data_show_state(self):
		self._data_show_state.append(True)

	
	def write_text(self, text_to_show=''):
		self.text_buffer.set_text(text_to_show)


	def refresh_text_box(self):
		self._set_final_string()		
		self.write_text(self._final_string)
		return True


	def _set_final_string(self):
		self._final_string = self._data_params[0]		 


	def set_data_params(self, param_id = 0 , value = None):
		"""
		Updates the parameters to show within the textbox
		Param_id	String
		0			string from sensors toolbar
		
		"""
		if param_id==0:
			self._data_params[0] = value
		else:
			pass


		self.refresh_text_box()
		
	
	def set_data_show_state(self, param_id = 0 , state = True):
		self._data_show_state[param_id] = state
					


