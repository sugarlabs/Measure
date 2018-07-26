#! /usr/bin/python
#
# Author:  Arjun Sarwal   arjun@laptop.org
# Copyright (C) 2007, Arjun Sarwal
# Copyright (C) 2009-12 Walter Bender
# Copyright (C) 2009, Benjamin Berg, Sebastian Berg
# Copyright (C) 2016, James Cameron [Gtk+ 3.0]
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA


from gi.repository import Gdk, Gtk
from math import floor, ceil
from numpy import array, where, int16, float64, multiply, fft, arange, blackman
from ringbuffer import RingBuffer1d

from config import MAX_GRAPHS, RATE, UPPER
from config import INSTRUMENT_DICT
from tuning_toolbar import A0, C8, freq_note

# Initialize logging.
import logging
log = logging.getLogger('measure-activity')
log.setLevel(logging.DEBUG)


class DrawWaveform(Gtk.DrawingArea):

    """ Handles all the drawing of waveforms """

    __gtype_name__ = "MeasureDrawWaveform"

    TRIGGER_NONE = 0
    TRIGGER_POS = 1
    TRIGGER_NEG = 2
    COLORS = ['#B20008', '#00588C', '#F8E800', '#7F00BF', '#4BFF3A', '#FFA109',
              '#00A0FF', '#BCCEFF', '#008009', '#F8E800', '#AC32FF', '#FFFFFF']

    def __init__(self, activity, input_frequency=RATE, channels=1):
        """ Initialize drawing area and scope parameter """
        super(type(self), self).__init__()

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.PROPERTY_CHANGE_MASK)

        self.activity = activity
        self._input_freq = input_frequency
        self.channels = channels
        self.triggering = self.TRIGGER_NONE
        self.trigger_xpos = 0.0
        self.trigger_ypos = 0.5

        self.y_mag = []  # additional scale factor for display
        self.gain = []
        self.bias = []  # vertical position fine-tuning from slider

        self.active = False

        self.buffers = array([])
        self.main_buffers = array([])
        self.str_buffer = ''
        self.peaks = []
        self.fftx = []

        self._tick_size = 50

        self.rms = ''
        self.avg = ''
        self.pp = ''
        self.count = 0
        self.invert = []

        self._freq_range = 4
        self.draw_interval = 10
        self.num_of_points = 115
        self.details_iter = 50
        self.c = 1180
        self.m = 0.0238
        self.k = 0.0238
        self.c2 = 139240  # c squared
        self.rms = 0
        self.avg = 0
        self.Rv = 0

        self._BACKGROUND_LINE_THICKNESS = 0.8
        self._TUNING_LINE_THICKNESS = 2
        self._HARMONIC_LINE_THICKNESS = 1
        self._TRIGGER_LINE_THICKNESS = 3
        self._FOREGROUND_LINE_THICKNESS = 6

        self.stop = False
        self.fft_show = False
        self.side_toolbar_copy = None

        self.scaleX = str(1.04167 / self.draw_interval) + ' ms'
        self.scaleY = ""

        self._back_surf = None

        self.pr_time = 0
        self.MAX_GRAPHS = MAX_GRAPHS     # Maximum simultaneous graphs

        self.graph_show_state = []
        self.Xstart = []
        self.Ystart = []
        self.Xend = []
        self.Yend = []
        self.color = []
        self.source = []
        self.graph_id = []
        self.visibility = []

        self.max_samples = 115
        self.max_samples_fact = 3

        self.time_div = 1.0
        self.freq_div = 1.0
        self.input_step = 1

        self.debug_str = 'start'

        self.instrument = None
        self.tuning_line = 0.0
        self.harmonics = False

        self.context = True

        for x in range(0, self.MAX_GRAPHS):
            self.graph_show_state.append(False)
            self.Xstart.append(0)
            self.Ystart.append(50)
            self.Xend.append(1000)
            self.Yend.append(500)
            self.color.append('#FF0000')
            self.source.append(0)
            self.visibility.append(True)
            self.graph_id.append(x)

        self.ringbuffer = []

        self._size_allocate_id = self.connect('size-allocate',
                                              self._size_allocate_cb)
        self._draw_id = self.connect('draw', self._draw_cb)

    def _to_rgba(self, colour):
        rgba = Gdk.RGBA(1.0, 1.0, 1.0, 1.0)
        rgba.parse(colour)
        return rgba

    def set_channels(self, channels):
        ''' Add buffer per channel '''
        self.channels = channels
        for i in range(min(self.channels, self.MAX_GRAPHS)):
            self.graph_show_state[i] = True
            self.Xstart[i] = 0
            self.Ystart[i] = 0
            self.Xend[i] = 1150
            self.Yend[i] = 750
            if i == 0:
                self.color[i] = self._to_rgba(self.activity.stroke_color)
            elif i == 1:
                self.color[i] = self._to_rgba(self.activity.fill_color)
            else:
                self.color[i] = self._to_rgba('#FFFFFF')
            self.source[i] = 0

        for i in range(self.channels):
            self.ringbuffer.append(RingBuffer1d(self.max_samples,
                                                dtype=int16))
            self.y_mag.append(3.0)
            self.gain.append(1.0)
            self.bias.append(0)
            self.invert.append(False)

    def set_max_samples(self, num):
        """ Maximum no. of samples in ringbuffer """
        if self.max_samples == num:
            return
        for i in range(self.channels):
            new_buffer = RingBuffer1d(num, dtype=int16)
            new_buffer.append(self.ringbuffer[i].read())
            self.ringbuffer[i] = new_buffer
        self.max_samples = num
        return

    def new_buffer(self, buf, channel=0):
        """ Append a new buffer to the ringbuffer """
        self.ringbuffer[channel].append(buf)
        return True

    def set_context_on(self):
        """ Return to an active state (context on) """
        if not self.context:
            self.handler_unblock(self._draw_id)
        self.context = True
        self._flush_redraw()
        return

    def set_context_off(self):
        """ Return to an inactive state (context off) """
        if self.context:
            self.handler_block(self._draw_id)
        self.context = False
        self._flush_redraw()
        return

    def set_invert_state(self, invert_state, channel=0):
        """ In sensor mode, we can invert the plot """
        self.invert[channel] = invert_state
        return

    def get_invert_state(self, channel=0):
        """ Return the current state of the invert flag """
        return self.invert[channel]

    def get_drawing_interval(self):
        """Returns the pixel interval horizontally between plots of two
        consecutive points"""
        return self.draw_interval

    def _size_allocate_cb(self, widget, allocation):
        """ Allocate a drawing area for the plot """
        self._update_mode()
        return

    def _flush_redraw(self):
        Gdk.flush()
        self.queue_draw()

    def do_button_press_event(self, event):
        """ Set the trigger position on a button-press event """
        self.trigger_xpos = event.x / float(self.get_allocated_width())
        self.trigger_ypos = event.y / float(self.get_allocated_height())
        return True

    def _calculate_trigger_position(self, samples, y_mag, buf):
        ''' If there is a trigger, we need to calculate an offset '''
        xpos = self.trigger_xpos
        ypos = self.trigger_ypos
        samples_to_end = int(samples * (1 - xpos))

        ypos -= 0.5
        if y_mag == 0:
            ypos *= -32767.0 / 0.01
        else:
            ypos *= -32767.0 / y_mag

        x_offset = self.get_allocated_width() * xpos - \
            (samples - samples_to_end) * self.draw_interval

        position = -1
        if self.triggering == self.TRIGGER_POS:
            sams = buf[samples - samples_to_end: - samples_to_end - 3]
            ints = sams <= ypos
            sams = buf[samples - samples_to_end + 1: - samples_to_end - 2]
            ints &= sams > ypos
            ints = where(ints)[0]
            if len(ints) > 0:
                position = max(position, ints[-1])
        elif self.triggering == self.TRIGGER_NEG:
            sams = buf[samples - samples_to_end: - samples_to_end - 3]
            ints = sams >= ypos
            sams = buf[samples - samples_to_end + 1: - samples_to_end - 2]
            ints &= sams < ypos
            ints = where(ints)[0]
            if len(ints) > 0:
                position = max(position, ints[-1])

        if position == -1:
            position = len(buf) - samples_to_end - 2
        else:
            position = position + samples - samples_to_end
            x_offset -= int(
                (float(-buf[position] + ypos) /
                 (buf[position + 1] - buf[position])) *
                self.draw_interval + 0.5)
        return position, samples_to_end

    def _draw_cb(self, widget, cr):
        w = self.get_allocated_width()
        h = self.get_allocated_height()

        # black background
        cr.set_source_rgb(0, 0, 0)
        cr.paint()

        # graticule
        cr.set_line_width(self._BACKGROUND_LINE_THICKNESS)
        cr.set_source_rgb(0.375, 0.375, 0.375)

        t = self._tick_size

        # vertical grid lines
        x = 0
        y = 0
        for j in range(0, w, t):
            cr.move_to(x, y)
            cr.rel_line_to(0, h)
            x += t

        # horizontal grid lines
        x = 0
        y = 0
        for j in range(0, h, t):
            cr.move_to(x, y)
            cr.rel_line_to(w, 0)
            y += t

        cr.stroke()

        # Real time drawing
        if self.context and self.active:

            # Draw tuning lines
            # If we are tuning, we want to scale by 10
            scale = 10. * self.freq_div / 500.
            if self.fft_show and self.instrument in INSTRUMENT_DICT:
                cr.set_line_width(self._TUNING_LINE_THICKNESS)
                for n, note in enumerate(INSTRUMENT_DICT[self.instrument]):
                    c = self._to_rgba(self.COLORS[n])
                    cr.set_source_rgb(c.red, c.green, c.blue)
                    x = int(note / scale)
                    cr.move_to(x, 0)
                    cr.line_to(x, h)
                    cr.stroke()
                if self.harmonics:
                    cr.set_line_width(self._HARMONIC_LINE_THICKNESS)
                    for n, note in enumerate(INSTRUMENT_DICT[self.instrument]):
                        c = self._to_rgba(self.COLORS[n])
                        cr.set_source_rgb(c.red, c.green, c.blue)
                        x = int(note / scale)
                        for i in range(3):
                            j = i + 2
                            cr.move_to(x * j, 20 * j)
                            cr.line_to(x * j, h)
                        cr.stroke()

            if self.fft_show and self.tuning_line > 0.0:
                x = int(self.tuning_line / scale)
                cr.set_line_width(self._TUNING_LINE_THICKNESS)
                c = self.color[1]
                cr.set_source_rgb(c.red, c.green, c.blue)
                cr.move_to(x, 0)
                cr.line_to(x, h)
                cr.stroke()
                if self.harmonics:
                    cr.set_line_width(self._HARMONIC_LINE_THICKNESS)
                    c = self.color[0]
                    cr.set_source_rgb(c.red, c.green, c.blue)
                    for i in range(3):
                        j = i + 2
                        cr.move_to(x * j, 20 * j)
                        cr.line_to(x * j, h)
                    cr.stroke()

            # Iterate for each graph
            for graph_id in self.graph_id:
                if not self.visibility[graph_id]:
                    continue
                if self.graph_show_state[graph_id]:
                    buf = self.ringbuffer[graph_id].read(None, self.input_step)
                    samples = int(ceil(w / self.draw_interval))
                    if len(buf) == 0:
                        # We don't have enough data to plot.
                        self._flush_redraw()
                        return

                    x_offset = 0
                    if not self.fft_show:
                        if self.triggering != self.TRIGGER_NONE:
                            position, samples_to_end = \
                                self._calculate_trigger_position(
                                    samples, self.y_mag[graph_id], buf)
                            sams = buf[position - samples + samples_to_end:
                                       position + samples_to_end + 2]
                        else:
                            sams = buf[-samples:]
                        data = sams.astype(float64)

                    else:
                        # FFT
                        try:
                            # Multiply input with the window
                            multiply(buf.astype(float64), self.fft_window,
                                     buf.astype(float64))

                            # Should be fast enough even without pow(2) stuff.
                            self.fftx = fft.rfft(buf)
                            self.fftx = abs(self.fftx)
                            data = multiply(self.fftx, 0.02, self.fftx)
                        except ValueError:
                            # TODO: Figure out how this can happen.
                            #       Shape mismatch between window and buf
                            self._flush_redraw()
                            return True

                    # Scaling the values
                    if self.activity.CONTEXT == 'sensor':
                        factor = 32767.0
                    else:
                        factor = 3276.70 * (UPPER - self.y_mag[graph_id])
                        if factor == 0:
                            factor = 0.01
                    if self.invert[graph_id]:
                        data *= h / factor
                    else:
                        data *= -h / factor
                    data -= self.bias[graph_id]

                    if self.fft_show:
                        data += h - 3
                    else:
                        data += (h / 2.0)

                    # The actual drawing of the graph
                    lines = (arange(len(data), dtype='float32') *
                             self.draw_interval) + x_offset
                    lines = list(zip(lines, data))

                    if self.fft_show:
                        n = data.argmin()
                        if self.tuning_line > 0 and \
                                n > 0 and n < len(lines) - 1:
                            # Interpolate
                            a, b, c = \
                                lines[n - 1][0], lines[n][0], lines[n + 1][0]
                            x = b - (a / float(a + b + c)) + (
                                c / float(a + b + c))
                            x *= scale
                            if x > A0 and x < C8:
                                self.activity.tuning_toolbar.label.set_markup(
                                    freq_note(x, flatsharp=True))
                    else:
                        if self.triggering != self.TRIGGER_NONE:
                            x = int(self.trigger_xpos * w)
                            y = int(self.trigger_ypos * h)
                            length = int(self._TRIGGER_LINE_THICKNESS * 3.5)
                            cr.set_line_width(self._TRIGGER_LINE_THICKNESS)
                            cr.set_source_rgb(0.6953125, 0.0, 0.03125)
                            cr.move_to(x - length, y)
                            cr.line_to(x + length, y)
                            cr.move_to(x, y - length)
                            cr.line_to(x, y - length +
                                       self._TRIGGER_LINE_THICKNESS)
                            cr.stroke()

                    cr.set_line_width(self._FOREGROUND_LINE_THICKNESS)
                    c = self.color[graph_id]
                    cr.set_source_rgb(c.red, c.green, c.blue)
                    cr.move_to(lines[0][0], lines[0][1])
                    for xy in lines[1:]:
                        cr.line_to(xy[0], xy[1])
                    cr.stroke()

            self._flush_redraw()

    def set_graph_source(self, graph_id, source=0):
        """Sets from where the graph will get data
        0 - uses from audiograb
        1 - uses from file"""
        self.source[graph_id] = source

    def set_div(self, time_div=0.0001, freq_div=10):
        """ Set division """
        self.time_div = time_div
        self.freq_div = freq_div

        self._update_mode()

    def get_trigger(self):
        return self.triggering

    def set_trigger(self, trigger):
        self.triggering = trigger

    def get_ticks(self):
        return self.get_allocated_width() / float(self._tick_size)

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
        if self.get_allocated_width() <= 0:
            return

        if self.fft_show:
            max_freq = (self.freq_div * self.get_ticks())
            wanted_step = 1.0 / max_freq / 2 * self._input_freq
            self.input_step = max(floor(wanted_step), 1)

            self.draw_interval = 5.0

            self.set_max_samples(
                ceil(self.get_allocated_width() /
                     float(self.draw_interval) * 2) * self.input_step)

            # Create the (blackman) window
            self.fft_window = blackman(
                ceil(self.get_allocated_width() /
                     float(self.draw_interval) * 2))

            self.draw_interval *= wanted_step / self.input_step
        else:
            # Factor is just for triggering:
            time = (self.time_div * self.get_ticks())
            if time == 0:
                return
            samples = time * self._input_freq
            self.set_max_samples(samples * self.max_samples_fact)

            self.input_step = max(ceil(samples /
                                       (self.get_allocated_width() / 3.0)), 1)
            self.draw_interval = self.get_allocated_width() / \
                (float(samples) / self.input_step)

            self.fft_window = None

    def set_active(self, active):
        self.active = active
        self._flush_redraw()

    def get_active(self):
        return self.active

    def get_mag_params(self, channel=0):
        return self.gain[channel], self.y_mag[channel]

    def set_mag_params(self, gain=1.0, y_mag=1.0, channel=0):
        self.gain[channel] = gain
        self.y_mag[channel] = y_mag

    def get_bias_param(self, channel=0):
        return self.bias[channel]

    def set_bias_param(self, bias=0, channel=0):
        self.bias[channel] = bias

    def set_visibility(self, state, channel=0):
        self.visibility[channel] = state

    def get_visibility(self, channel=0):
        return self.visibility[channel]
