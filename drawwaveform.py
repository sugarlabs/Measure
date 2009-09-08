#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2009, Walter Bender
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

import pygst
pygst.require("0.10")
import pygtk
import gtk
import cairo
import gobject
import time
from struct import unpack
import pango
import os
import audioop
import math
from gtk import gdk
try:
    import gconf
except:
    from sugar import profile
from numpy.oldnumeric import *
from numpy.fft import *

from gettext import gettext as _

import config  	#This has all the globals


class DrawWaveform(gtk.DrawingArea):

    def __init__(self):

        gtk.DrawingArea.__init__(self)

        self.buffers = []
        self.str_buffer=''
        self.buffers_temp=[]
        self.integer_buffer=[]	
        self.peaks = []
        self.main_buffers = []
        self.fftx = []

        self.rms=''
        self.avg=''
        self.pp=''	
        self.count=0
        self.invert=False

        self.param1= config.WINDOW_H/65536.0
        self.param2= config.WINDOW_H/2.0	
        self.y_mag = 3.0
        self.g = 1  #Gain (not in dB) introduced by Capture Gain and Mic Boost    
        self._freq_range = 4 #See comment in sound_toolbar.py re freq_range
        self.draw_interval = 10
        self.num_of_points = 115
        self.details_iter = 50
        self.c = 1180
        self.m = 0.0238
        self.k = 0.0238
        self.c2 = 139240	#c squared
        self.t_x = (int)(config.TEXT_X_M*config.WINDOW_W)
        self.t_y = (int)(config.TEXT_Y_M*config.WINDOW_H)
        self.rms = 0
        self.avg = 0
        self.Rv = 0
	# constant to multiply with self.param2 while scaling values 
        self.y_mag_bias_multiplier = 1
        self.log_param1 = ""
        self.log_param2 = ""
        self.log_param3 = ""
        self.log_param4 = ""
        self.log_param5 = ""

        self._BACKGROUND_LINE_THICKNESS =  0.8
        self._FOREGROUND_LINE_THICKNESS = 6

        self.logging_status = False
        self.f = None
        self.stop = False
        self.fft_show = False
        self.side_toolbar_copy = None

        self.scaleX = str( 1.04167/self.draw_interval ) + " ms"
        self.scaleY = ""


        self._line_gc = None
        self._back_surf = None		
        self.pango_context = self.create_pango_context()
        #self.font_desc = pango.FontDescription('Serif 6')
        self.expose_event_id = self.connect("expose_event", self._expose)



        self.pr_time = 0
        self.MAX_GRAPHS = config.MAX_GRAPHS     #Maximum simultaneous graphs

        self.graph_show_state=[]
        self.Xstart =[]
        self.Ystart = []
        self.Xend  = []
        self.Yend  = []
        self.type   = []
        self.color  = []
        self.source    = []
        self.graph_id = []

        for x in range (0, self.MAX_GRAPHS):
	        self.graph_show_state.append(False)
	        self.Xstart.append(0)
	        self.Ystart.append(50)
	        self.Xend.append(1000)
	        self.Yend.append(500)
	        self.type .append(0)
	        self.color.append([65535,0,0])
	        self.source.append(0)
	        self.graph_id.append(x)

        self.graph_show_state[0]=True
        self.Xstart[0] = 0
        self.Ystart[0] = 0
        self.Xend[0] = 1150
        self.Yend[0] = 750
        self.type[0]  = 0
        self.color[0]  = [65535,0,65535]
        self.source[0] = 0

        """
        self.graph_show_state[1]=True
        self.Xstart[0] = 0
        self.Ystart[1] = 0
        self.Xend[0] = 800
        self.Yend[1] = 600
        self.type[1]  = 0
        self.color[1]  = [0,65535,65535]
        self.source[1] = 0

        self.graph_show_state[2]=True
        self.Xstart[2] = 30
        self.Ystart[2] = 0
        self.Xend[2] = 300
        self.Yend[2] = 300
        self.type[2]  = 0
        self.color[2]  = [0,65535,0]
        self.source[2] = 0

        self.graph_show_state[3]=True
        self.Xstart[3] = 0
        self.Ystart[3] = 300
        self.Xend[3] = 1000
        self.Yend[3] = 700
        self.type[3]  = 0
        self.color[3]  = [65535,65535,0]
        self.source[3] = 0
        """

        self.max_samples = 115

        self.debug_str="start"

        self.context = True

    def new_buffer(self, buf):
        buf = str(buf)
        self.str_buffer = buf
        tmp_val = (self.max_samples - 1)
        self.integer_buffer = list(unpack( str(int(len(buf))/2)+'h' , buf))		
        if(len(self.main_buffers)>tmp_val):
	        del self.main_buffers[0:(len(self.main_buffers)-tmp_val)]
        self.main_buffers += self.integer_buffer
        return True

    def set_context_on(self):
        self.handler_unblock(self.expose_event_id)
        self.context = True

    def set_context_off(self):
        self.context = False
        self.handler_block(self.expose_event_id)

    def set_invert_state(self, invert_state):
        self.invert = invert_state

    def get_invert_state(self):
        return self.invert

    def get_drawing_interval(self):
        """Returns the pixel interval horizontally between plots of two 
        consecutive points"""
        return self.draw_interval

    def _init_background(self):
        if self._back_surf:
	        return

        colmap = self.get_colormap()
        clr = colmap.alloc_color(0, 65535, 0, False, False)
        self._line_gc = self.window.new_gc(foreground = clr)
        self._line_gc.set_line_attributes(self._FOREGROUND_LINE_THICKNESS,\
                                          gdk.LINE_SOLID,\
	                                  gdk.CAP_ROUND, gdk.JOIN_BEVEL)   

        self._back_surf = gdk.Pixmap(self.window, int(config.WINDOW_W), \
	                             int(config.WINDOW_H))
        cr = self._back_surf.cairo_create()
	                    
        #background
        cr.set_source_rgb(0, 0, 0)
        cr.rectangle(0, 0, config.WINDOW_W, config.WINDOW_H)
        cr.fill()

        #grid
        cr.set_line_width(self._BACKGROUND_LINE_THICKNESS)
        cr.set_source_rgb(0.2, 0.2, 0.2)

        x = 0
        y = 0

        for j in range(1, 25):
	        cr.move_to(x, y)
	        cr.rel_line_to(0, config.WINDOW_H)
	        x = x + 50

        cr.set_line_width(self._BACKGROUND_LINE_THICKNESS)
        x = 0
        y = 0

        for j in range(1, 17):
	        cr.move_to(x, y)
	        cr.rel_line_to(config.WINDOW_W, 0)
	        y = y + 50

        cr.stroke()	

    def _expose(self, widget, event):
        """This function is the "expose" event handler and does all the 
        drawing"""

        ##################### Real time drawing ###################
        if(self.context == True):

            #Draw the background
            #We could probably make this faster with another pixmap.
            self._init_background()
            self.window.draw_drawable(self.get_style().bg_gc[0], \
                                      self._back_surf, 0, 0, 0, 0, \
                                      config.WINDOW_W, config.WINDOW_H)
            #Iterate for each graph 
            for graph_id in self.graph_id:
                if self.graph_show_state[graph_id] == True:  
                    span = self.Xend[graph_id]-self.Xstart[graph_id]

                    if self._freq_range == 1:
                        self.draw_interval = 4
                        self.max_samples = span/self.draw_interval
                    else:
                        if span>=700:
                            self.draw_interval = 10
                        elif span<700 and span>=500:
                            self.draw_interval = 7
                        elif span<500 and span>=300:
                            self.draw_interval = 5
                        else:
                            self.draw_interval = 3
                        self.max_samples = span/self.draw_interval

                    if(len(self.main_buffers)>=self.max_samples):
                        del self.main_buffers[0:(len(self.main_buffers)-\
                                                (self.max_samples+1))]
		          
                    if(self.fft_show==False):				
                        self.y_mag_bias_multiplier = 1					
                        """ Depending upon the X span of the graph, deciding 
                        the total number of points to take """
                    else:
                        ############## FFT ###############		
                        Fs = 48000
                        nfft = 65536
                        if self.integer_buffer:
                            self.integer_buffer = self.integer_buffer[0:256]
                            self.fftx = fft(self.integer_buffer, 256,-1)
                            self.fftx = self.fftx[0:self.max_samples]
                            self.main_buffers = [(abs(x) * 0.02) \
                                                for x in self.fftx]
                            self.y_mag_bias_multiplier=0.1
                        ##################################
                                    
							                
                    ################ Getting data #################
                    if self.source[graph_id]==0:
                        self.buffers=self.main_buffers
                    else:
                        pass  #write code here that gets data from file
                    ###############################################

                    ########### Scaling the values ################
                    if config.CONTEXT == 2:
                        self.y_mag = 1
                        self.y_mag_bias_multiplier = 1
                    self.param2= (self.Yend[graph_id]-self.Ystart[graph_id])/2.0
                    self.param1= self.param2/32768.0

                    val=[]
                    for i in self.buffers:
                        # only apply invert to time display
                        if self.invert is True and self.fft_show is False:
                            temp_val_float = -(self.param1*i*self.y_mag) +\
                                        (self.param2*self.y_mag_bias_multiplier)
                        else:
                            temp_val_float = (self.param1*i*self.y_mag) +\
                                        (self.param2*self.y_mag_bias_multiplier)
                        if(temp_val_float>=self.Yend[graph_id]):
                            temp_val_float= self.Yend[graph_id]
                        if(temp_val_float<=self.Ystart[graph_id]):
                            temp_val_float= self.Ystart[graph_id]
                        val.append( config.WINDOW_H - temp_val_float  )

                    self.peaks=val
                    ###############################################

                    ###### The actual drawing of the graph ########
                    """TODO: Improvement : The color setting shouldn't happen
                    in every drawing loop, should happen only once"""
                    colmap = self.get_colormap()
                    r,g,b = self.get_stroke_color_from_sugar()
                    clr = colmap.alloc_color( r, g, b, False, False)					
                    self._line_gc.set_foreground(clr)

                    count = self.Xstart[graph_id]
                    lines = []
                    for peak in self.peaks:
                        lines.append((count, peak))
                        count = count + self.draw_interval

                    if self.type[graph_id] ==0:
                        self.window.draw_lines(self._line_gc, lines)
                    else:
                        self.window.draw_points(self._line_gc, lines)
                    ###############################################
                    
        """
        ## DISPLAYING FRAMERATE FOR DEBUGGGIN
        fr = 1.0/( time.time()-self.pr_time)
        self.pr_time=time.time()
        layout = pango.Layout(self.pango_context)
        layout.set_text(str(fr) +self.debug_str)
        self.window.draw_layout(self.get_style().white_gc, self.t_x, self.t_y,\
                                layout)
        """
        return True

    def set_side_toolbar_reference(self, side_toolbar):
        self.side_toolbar_copy = side_toolbar

    def set_electrical_ui_reference(self, electrical_ui):
        self.electrical_ui_copy = electrical_ui

    def set_graph_source(self, graph_id, source=0):
        """Sets from where the graph will get data 
        0 - uses from audiograb
        1 - uses from file"""
        self.source[graph_id] = source

    def set_graph_params(self, graph_id, Xstart, Ystart, Xend, Yend, type,\
                         color):
        """Sets Xstart, Ystart --> the bottom left co-ordinates
        Xend, Yend             --> the top right co-ordinates
        type                   --> 0 for a connected graph, 1 for a dotted graph
        color                  --> what color graph to draw"""
        self.Xstart[graph_id] = Xstart
        self.Ystart[graph_id] = Ystart
        self.Xend[graph_id] = Xend
        self.Yend[graph_id] = Yend
        self.type[graph_id]  = type
        self.color[graph_id]  = color

    def get_fft_mode(self):
        """Returns if FFT is ON (True) or OFF (False)"""
        return self.fft_show

    def set_fft_mode(self, fft_mode=False):
        """Sets whether FFT mode is ON (True) or OFF (False)"""
        self.fft_show = fft_mode

    def set_freq_range(self, freq_range=4):
        """See sound_toolbar to see what all frequency ranges are"""
        self._freq_range = freq_range

    def get_stroke_color_from_sugar(self):
        """Returns in (r,g,b) format the stroke color from the Sugar profile"""
        try:
            client = gconf.client_get_default()
            color = client.get_string("/desktop/sugar/user/color")
        except:
            color = profile.get_color().to_string()
        stroke,fill = color.split(",")
        colorstring = stroke.strip()
        if colorstring[0] == '#': 
            colorstring = colorstring[1:]
	    r,g,b = colorstring[:2], colorstring[2:4], colorstring[4:]
	    r+="00"
	    g+="00"
	    b+="00"
	    r,g,b = [int(n, 16) for n in (r,g,b)]
        return (r,g,b)

    def get_fill_color_from_sugar(self):
        """Returns in (r,g,b) format the fill color from the Sugar profile"""
        try:
            client = gconf.client_get_default()
            color = client.get_string("/desktop/sugar/user/color")
        except:
            color = profile.get_color()
        stroke,fill = color.split(",")
        colorstring = fill.strip()
        if colorstring[0] == '#': 
            colorstring = colorstring[1:]
	    r,g,b = colorstring[:2], colorstring[2:4], colorstring[4:]
	    r+="00"
	    g+="00"
	    b+="00"
	    r,g,b = [int(n, 16) for n in (r,g,b)]
        return (r,g,b)

    def get_mag_params(self):
        return self.g, self.y_mag

    def set_mag_params(self, g=1.0, y_mag=3.0):
        self.g = g
        self.y_mag = y_mag
