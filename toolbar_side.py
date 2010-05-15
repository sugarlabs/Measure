#! /usr/bin/python
import pygtk
import gtk

import config  	#This has all the globals


class SideToolbar(gtk.DrawingArea):

    def __init__(self, activity):
        gtk.DrawingArea.__init__(self)

        self.wave_copy = activity.wave
        self.ag = activity.audiograb
        self.show_toolbar = True

        self.adjustmenty = gtk.Adjustment(3.0, 0.0, 4.0 ,0.1, 0.1, 0.0)
        self.adjustmenty.connect("value_changed", self.cb_page_sizey,\
	        self.adjustmenty)
        self.yscrollbar = gtk.VScale(self.adjustmenty)
        self.yscrollbar.set_draw_value(False)
        self.yscrollbar.set_inverted(True)
        self.yscrollbar.set_update_policy(gtk.UPDATE_CONTINUOUS)
		
        self.img_amphigh = gtk.Image()
        self.img_amplow =  gtk.Image()		

        self.img_amphigh.set_from_file(config.ICONS_DIR + '/amp-high.svg')
        self.img_amplow.set_from_file(config.ICONS_DIR + '/amp-low.svg')

        self.box1 = gtk.VBox(False,0)
        self.box1.pack_start(self.img_amphigh, False, True, 0)
        self.box1.pack_start(self.yscrollbar, True, True, 0)
        self.box1.pack_start(self.img_amplow, False, True, 0)

        ##test  
        self.set_show_hide(False)


    def cb_page_sizey(self, get, data=None):
        if(get.value<=1.5):		
            self.wave_copy.y_mag= get.value
            self.ag.set_capture_gain(0)
            self.wave_copy.g = 1            #0dB
        if(get.value>1.5 and get.value<=2.5 ):
            self.wave_copy.y_mag= (get.value*1.5)		
            self.ag.set_capture_gain(25)
            self.wave_copy.g = 1.9952       #6dB
        if(get.value>2.5 and get.value<=3.5 ):
            self.wave_copy.y_mag= (get.value*3)
            self.ag.set_capture_gain(50)
            self.wave_copy.g = 3.981        #12dB
        if(get.value>3.5 and get.value<=4.0 ):
            self.wave_copy.y_mag= (get.value*4)
            self.ag.set_capture_gain(100)
            self.wave_copy.g = 13.335       #22.5dB
        return True	


    def set_show_hide(self, show=True):
        self.show_toolbar = show
        #self.yscrollbar.show(self.show_toolbar)

    def get_show_hide(self):
        return self.show_toolbar
