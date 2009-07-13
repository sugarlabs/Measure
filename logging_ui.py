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
from sugar.graphics.menuitem  import MenuItem


class LogToolbar(gtk.Toolbar):
    """This class allows one to control throught the toolbar, writing values onto a csv file and hance implement one or many logging sessions"""
    
    def __init__(self, audiograb, journal, activity):
        
        gtk.Toolbar.__init__(self)

        self.ag = audiograb
        self.ji = journal
        self.activity = activity
        
        
        self.loginterval_img = gtk.Image()
        self.loginterval_img.set_from_file(config.ICONS_DIR + '/sample_rate.svg')
        self.loginterval_img_tool = gtk.ToolItem()
        self.loginterval_img_tool.add(self.loginterval_img)
        self.insert(self.loginterval_img_tool,-1)
        self.loginterval_img.show()
        self.loginterval_img_tool.show()

        #######################Logging Interval#####################
        self._loginterval_combo = ComboBox()
        self.interval = [_('Picture'), _('1 second') , _('5 seconds'),  _('1 minute') , _('5 minutes'),  _('1 hour')]
        
        self._interval_changed_id = self._loginterval_combo.connect("changed", self.loginterval_control)

        for i, s in enumerate(self.interval):
            self._loginterval_combo.append_item(i, s, None)
            if s == _('Picture'):
                self._loginterval_combo.set_active(i)
        
        self._loginterval_tool = ToolComboBox(self._loginterval_combo)
        self.insert(self._loginterval_tool,-1)
        self._loginterval_tool.show()
        self.logginginterval_status = 'picture'		
        ############################################################

        separator = gtk.SeparatorToolItem()
        separator.set_draw(True)
        self.insert(separator, -1)
        separator.show()

        #######################Start Logging/Stop Logging#####################
        self._record = ToolButton('media-record')
        self.insert(self._record, -1)
        self._record.show()
        self._record.set_tooltip(_('Start Logging'))
        self.record_state = False  	    #True means recording in progress, False means not recording
        self._record.connect('clicked', self.record_control)
        ######################################################################

        separator = gtk.SeparatorToolItem()
        separator.set_draw(True)
        self.insert(separator, -1)
        separator.show()


    def record_control(self, data=None):
        """Depending upon the selected interval, does either
        a logging session, or just logs the current buffer"""
        if self.record_state == False:
            Xscale = (1.00/self.ag.get_sampling_rate())
            Yscale = 0.0
            interval = self.interval_convert()
            self.ji.start_new_session("arjs", Xscale, Yscale)
            self.ag.set_logging_params(True, interval)
            self.record_state = True
            
            self._record.set_icon('media-playback-stop')
            self._record.show()
            self._record.set_tooltip(_('Stop Logging'))
            if interval==0:
                self._record.set_icon('media-record')
                self._record.show()
                self._record.set_tooltip(_('Start Logging'))
                self.record_state = False
        else:
            self.ji.stop_session()
            self.ag.set_logging_params(False)
            self.record_state = False
            
            self._record.set_icon('media-record')
            self._record.show()
            self._record.set_tooltip(_('Start Logging'))


    def interval_convert(self):
        """Converts picture/1second/5seconds/1minute/5minutes to an integer
        which denotes the number of times the audiograb buffer must be called before a value is written.
        When set to 0, the whole of current buffer will be written"""
        if self.logginginterval_status == 'picture':
            return 0
        elif self.logginginterval_status == 'second':
            return 50
        elif self.logginginterval_status == '5second':
            return 250
        elif self.logginginterval_status == 'minute':
            return 3000
        elif self.logginginterval_status == '5minute':
            return 15000
        elif self.logginginterval_status == 'hour':
            return 180000
            
            

    def loginterval_control(self, combobox):

        if (self._loginterval_combo.get_active() != -1):
            if (self._loginterval_combo.get_active() == 0):
                self.logginginterval_status = 'picture'		
            if (self._loginterval_combo.get_active() == 1):
                self.logginginterval_status = 'second'		
            if (self._loginterval_combo.get_active() == 2):
                self.logginginterval_status = '5second'		
            if (self._loginterval_combo.get_active() == 3):
                self.logginginterval_status = 'minute'		
            if (self._loginterval_combo.get_active() == 3):
                self.logginginterval_status = '5minute'		
            if (self._loginterval_combo.get_active() == 3):
                self.logginginterval_status = 'hour'		
