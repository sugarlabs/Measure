#! /usr/bin/python
import pygtk
import gtk

import config  	#This has all the globals


class SideToolbar(gtk.DrawingArea):

    def __init__(self, activity):
        gtk.DrawingArea.__init__(self)

        self.wave = activity.wave
        self.ag = activity.audiograb
        self.show_toolbar = True

        self.mode = config.SOUND

        self.adjustmenty = gtk.Adjustment(3.0, 0.0, 4.0, 0.1, 0.1, 0.0)
        self.adjustmenty.connect("value_changed", self.cb_page_sizey,
	        self.adjustmenty)
        self.yscrollbar = gtk.VScale(self.adjustmenty)
        self.yscrollbar.set_draw_value(False)
        self.yscrollbar.set_inverted(True)
        self.yscrollbar.set_update_policy(gtk.UPDATE_CONTINUOUS)
		
        self.img_high = gtk.Image()
        self.img_low =  gtk.Image()		

        self.img_high.set_from_file(config.ICONS_DIR + '/amp-high.svg')
        self.img_low.set_from_file(config.ICONS_DIR + '/amp-low.svg')

        self.box1 = gtk.VBox(False,0)
        self.box1.pack_start(self.img_high, False, True, 0)
        self.box1.pack_start(self.yscrollbar, True, True, 0)
        self.box1.pack_start(self.img_low, False, True, 0)

        ##test  
        self.set_show_hide(False)

    def cb_page_sizey(self, adjy, data=None):
        if self.mode == config.SOUND:
            if(adjy.value<=1.5):	
                self.wave.set_mag_params(1.0, adjy.value)        #0dB
                self.ag.set_capture_gain(0)
            elif(adjy.value>1.5 and adjy.value<=2.5 ):
                self.wave.set_mag_params(1.9952, adjy.value*1.5) #6dB
                self.ag.set_capture_gain(25)
            elif(adjy.value>2.5 and adjy.value<=3.5 ):
                self.wave.set_mag_params(3.981, adjy.value*3.0) #12dB
                self.ag.set_capture_gain(50)
            else:
                self.wave.set_mag_params(13.335, adjy.value*4.0) #22.5dB
                self.ag.set_capture_gain(100)
            self.wave.set_bias_param(0)
        else:
            self.wave.set_bias_param(int((adjy.value-2)*300))
        return True	

    def set_show_hide(self, show=True, mode=config.SOUND):
        self.show_toolbar = show
        self.set_mode(mode)
        #self.yscrollbar.show(self.show_toolbar)

    def get_show_hide(self):
        return self.show_toolbar

    def set_mode(self, window_id=1):
        self.mode = window_id
        if self.mode == config.SOUND:
            self.img_high.set_from_file(config.ICONS_DIR + '/amp-high.svg')
            self.img_low.set_from_file(config.ICONS_DIR + '/amp-low.svg')
        else:
            self.img_high.set_from_file(config.ICONS_DIR + '/bias-high.svg')
            self.img_low.set_from_file(config.ICONS_DIR + '/bias-low.svg')
        return
