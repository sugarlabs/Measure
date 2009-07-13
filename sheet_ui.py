"""
import pygtk
import gtk
import gobject
from gettext import gettext as _


import config  	#This has all the globals

from sugar.activity.activity import ActivityToolbox, EditToolbar
from sugar.graphics.toolcombobox import ToolComboBox
from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.toggletoolbutton import ToggleToolButton
from sugar.graphics.combobox import ComboBox
from sugar.graphics.menuitem import MenuItem

class SheetToolbar(gtk.Toolbar):

    def __init__(self, sheet, activity):
        
        gtk.Toolbar.__init__(self)

        self.activity = activity
        
        self._sheet_show = ToolButton('media-record')
        self.insert(self._sheet_show, -1)
        self._sheet_show.show()
        self._sheet_show.set_tooltip(_('Show sheet and graphs'))
        self._sheet_show.connect('clicked', self.sheet_show_control)
        self.show_window = 'wave'  #other is sheet
        
    """
    def sheet_show_control(self, data=None):
        """Controls whether to show the real time waveform or the sheet+graph interface"""
        if self.show_window=='sheet':
            self.activity.set_show_hide_windows(0)
            self._sheet_show.set_tooltip(_('Show sheet and graphs'))
            self.show_window='wave'
            return
        elif self.show_window=='wave':
            self.activity.set_show_hide_windows(1)
            self._sheet_show.set_tooltip(_('Show waveform'))
            self.show_window='sheet'
            return
            
        
