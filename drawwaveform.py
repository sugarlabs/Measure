#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2009, Walter Bender
#    Copyright (C) 2009, Benjamin Berg, Sebastian Berg
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
import cairo
import gobject
import time
import pango
import os
import audioop
import math
import numpy as np
from ringbuffer import RingBuffer1d
from gtk import gdk
try:
    import gconf
except:
    from sugar import profile

from gettext import gettext as _

import config  	#This has all the globals


class DrawWaveform(gtk.DrawingArea):

    __gtype_name__ = "MeasureDrawWaveform"

    def __init__(self, input_frequency=48000):

        gtk.DrawingArea.__init__(self)

        self._input_freq = input_frequency
        self.stroke_color = None
        self.triggering = True

        self.buffers = np.array([])
        self.main_buffers = np.array([])
        self.str_buffer=''
        self.peaks = []
        self.fftx = []

        self._tick_size = 50

        self.rms=''
        self.avg=''
        self.pp=''
        self.count=0
        self.invert=False

        self.y_mag = 3.0
        self.g = 1  #Gain (not in dB) introduced by Capture Gain and Mic Boost
        self._freq_range = 4 #See comment in sound_toolbar.py to see what different ranges are all about
        self.draw_interval = 10
        self.num_of_points = 115
        self.details_iter = 50
        self.c = 1180
        self.m = 0.0238
        self.k = 0.0238
        self.c2 = 139240    #c squared
        self.rms = 0
        self.avg = 0
        self.Rv = 0
        # constant to multiply with self.param2 while scaling values 
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
        self.color[0]  = self.get_stroke_color_from_sugar()
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
        self.max_samples_fact = 3
        
        self.time_div = 1.
        self.freq_div = 1.
        self.input_step = 1
        
        self.ringbuffer = RingBuffer1d(self.max_samples, dtype='int16')

        self.debug_str="start"

        self.context = True
        

    def set_max_samples(self, num):
        if self.max_samples == num:
            return
        new_buffer = RingBuffer1d(num, dtype='int16')
        
        new_buffer.append(self.ringbuffer.read())
        self.ringbuffer = new_buffer
        self.max_samples = num

    def new_buffer(self, buf):
        self.ringbuffer.append(buf)
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

    def do_size_allocate(self, allocation):
        gtk.DrawingArea.do_size_allocate(self, allocation)
        self._update_mode()

    def do_realize(self):
        gtk.DrawingArea.do_realize(self)

        colormap = self.get_colormap()

        self._line_gc = []
        for graph_id in self.graph_id:
            r, g, b = self.color[graph_id]
            clr = colormap.alloc_color(r, g, b, False, False)

            self._line_gc.append(self.window.new_gc(foreground=clr))
            self._line_gc[graph_id].set_line_attributes( \
                self._FOREGROUND_LINE_THICKNESS, gdk.LINE_SOLID, \
                gdk.CAP_ROUND, gdk.JOIN_BEVEL)   

            self._line_gc[graph_id].set_foreground(clr)
  
        # Background pixmap
        clr = colormap.alloc_color(0, 65535, 0, False, False)

        back_surf = gdk.Pixmap(self.window, self._tick_size, self._tick_size)
        cr = back_surf.cairo_create()

        #background
        cr.set_source_rgb(0, 0, 0)
        cr.paint()

        #grid
        cr.set_line_width(self._BACKGROUND_LINE_THICKNESS)
        cr.set_source_rgb(0.2, 0.2, 0.2)

        x = 0
        y = 0

        for j in range(0, 2):
            cr.move_to(x, y)
            cr.rel_line_to(0, self._tick_size)
            x = x + self._tick_size

        x = 0
        y = 0

        for j in range(0, 2):
            cr.move_to(x, y)
            cr.rel_line_to(self._tick_size, 0)
            y = y + self._tick_size

        cr.set_line_width(self._BACKGROUND_LINE_THICKNESS)
        cr.stroke()

        del cr
        self.window.set_back_pixmap(back_surf, False)

    def _expose(self, widget, event):
        """This function is the "expose" event handler and does all the drawing"""
        #######################Real time drawing###################################
        if self.context:

            #Iterate for each graph                                                            
            for graph_id in self.graph_id:                                          
                if self.graph_show_state[graph_id] == True:
                    buf = self.ringbuffer.read(None, self.input_step)
                    samples = math.ceil(self.allocation.width/self.draw_interval)
                    if len(buf) == 0:
                        # We don't have enough data to plot.
                        return

                    x_offset = 0

                    if (self.fft_show==False):
                        if self.triggering == True:
                            ints = buf[:-samples-3] <= 0
                            ints &= buf[1:-samples-2] > 0

                            ints = np.where(ints)[0]
                            if len(ints) == 0:
                                ints = len(buf) - samples
                            else:
                                ints = ints[-1]
                                x_offset = int((float(-buf[ints])/(buf[ints+1]-buf[ints]))*self.draw_interval+0.5)

                            data = buf[ints:ints+samples+2].astype(np.float64)
                        else:
                            data = buf[-samples:].astype(np.float64)

                    else:
                        ###############FFT################ 
                        Fs = 48000
                        nfft = 65536

                        # Multiply input with the window
                        np.multiply(buf, self.fft_window, buf)

                        # Should be fast enough even without power of 2 stuff.
                        self.fftx = np.fft.rfft(buf)
                        self.fftx = abs(self.fftx)
                        data = np.multiply(self.fftx, 0.02, self.fftx)
                        ##################################

                    ################Scaling the values###################
                    if config.CONTEXT == 2:
                        self.y_mag = 1

                    data *= (-self.allocation.height/32767.0 * self.y_mag)
                    if self.fft_show:
                        data += self.allocation.height - 3
                    else:
                        data += (self.allocation.height/2.0)

                    ################################################

                    ##########The actual drawing of the graph##################

                    lines = (np.arange(len(data), dtype='float32') * self.draw_interval) - x_offset

                    # We must make sure its int, or draw_lines will throw warnings
                    # and these warnings are slow (even though they are filtered)!
                    lines = zip(lines.astype('int'), data.astype('int'))

                    if self.type[graph_id] ==0:
                        self.window.draw_lines(self._line_gc[graph_id], lines)
                    else:
                        self.window.draw_points(self._line_gc[graph_id], lines)
                    ############################################################
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

    def set_div(self, time_div=0.0001, freq_div=10):
        """Set division
        """        
        self.time_div = time_div
        self.freq_div = freq_div

        self._update_mode()

    def get_ticks(self):
        return self.allocation.width/float(self._tick_size)

    def get_fft_mode(self):
        """Returns if FFT is ON (True) or OFF (False)"""
        return self.fft_show

    def set_fft_mode(self, fft_mode=False):
        """Sets whether FFT mode is ON (True) or OFF (False)"""
        self.fft_show = fft_mode
        self._update_mode()

    def set_freq_range(self, freq_range=4):
        """See sound_toolbar to see what all frequency ranges are"""
        self._freq_range = freq_range

    def _update_mode(self):        
        if self.allocation.width <= 0:
            return

        if self.fft_show:
            max_freq = (self.freq_div*self.get_ticks())
            wanted_step = 1.0/max_freq/2*self._input_freq
            self.input_step = max(math.floor(wanted_step), 1)

            self.draw_interval = 5.0

            self.set_max_samples(math.ceil(self.allocation.width/float(self.draw_interval)*2)*self.input_step)

            # Create the (blackman) window
            self.fft_window = np.blackman(math.ceil(self.allocation.width/float(self.draw_interval)*2))

            self.draw_interval *= wanted_step/self.input_step
        else:
            # Factor is just for triggering:
            time = (self.time_div*self.get_ticks())
            if time == 0:
                return
            samples = time * self._input_freq
            self.set_max_samples(samples * self.max_samples_fact)

            self.input_step = max(math.ceil(samples/(self.allocation.width/3.0)),1)
            self.draw_interval = self.allocation.width/(float(samples)/self.input_step)

            self.fft_window = None

    def get_stroke_color_from_sugar(self):
        """Returns in (r,g,b) format the stroke color from the Sugar profile"""
        # Hitting gconf is a large overhead.
        if self.stroke_color is None:
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
	        r+=r
	        g+=g
	        b+=b
	        r,g,b = [int(n, 16) for n in (r,g,b)]
	        self.stroke_color = (r,g,b)

        return self.stroke_color

    #def get_fill_color_from_sugar(self):
    #    """Returns in (r,g,b) format the fill color from the Sugar profile"""
    #    # Hitting gconf is a large overhead.
    #    if self.fill_color is None:
    #        try:
    #            client = gconf.client_get_default()
    #            color = client.get_string("/desktop/sugar/user/color")
    #        except:
    #            color = profile.get_color().to_string()
    #        stroke,fill = color.split(",")
    #        colorstring = fill.strip()
    #        if colorstring[0] == '#': 
    #            colorstring = colorstring[1:]
	#        r,g,b = colorstring[:2], colorstring[2:4], colorstring[4:]
	#        r+=r
	#        g+=g
	#        b+=b
	#        r,g,b = [int(n, 16) for n in (r,g,b)]
	#        self.fill_color = (r,g,b)
    #
    #    return self.stroke_color = (r,g,b)

    def get_mag_params(self):
        return self.g, self.y_mag

    def set_mag_params(self, g=1.0, y_mag=3.0):
        self.g = g
        self.y_mag = y_mag

