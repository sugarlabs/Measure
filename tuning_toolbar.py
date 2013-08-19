# -*- coding: utf-8 -*-
#! /usr/bin/python
#
# Copyright (C) 2009-12 Walter Bender
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA

import os

import gtk
import gobject

from gettext import gettext as _

from config import XO4, XO175, INSTRUMENT_DICT
from audiograb import check_output

from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.menuitem import MenuItem
from sugar.graphics import style

import logging
log = logging.getLogger('measure-activity')
log.setLevel(logging.DEBUG)


NOTES = ['A', 'A♯/B♭', 'B', 'C', 'C♯/D♭', 'D', 'D♯/E♭', 'E', 'F', 'F♯/G♭',
         'G', 'G♯/A♭']
SHARP = '♯'
FLAT = '♭'
A0 = 27.5
C8 = 4186.01
TWELTHROOT2 = 1.05946309435929
COLOR_RED = style.Color('#FF6060')
COLOR_YELLOW = style.Color('#FFFF00')
COLOR_GREEN = style.Color('#00FF00')
SPAN = '<span foreground="%s"><big><b>%s</b></big></span>'


class TuningToolbar(gtk.Toolbar):
    ''' The toolbar for tuning instruments '''

    def __init__(self, activity):
        gtk.Toolbar.__init__(self)

        self.activity = activity
        self._show_tuning_line = False
        self._updating_note = True
        self._tuning_tool = None

        self._instrument_button = ToolButton('instruments')
        self._instrument_button.set_tooltip(_('Tune an instrument.'))
        self._instrument_button.connect('clicked',
                                        self._button_selection_cb)
        self.insert(self._instrument_button, -1)
        self._setup_instrument_palette()

        separator = gtk.SeparatorToolItem()
        separator.props.draw = True
        self.insert(separator, -1)

        self._note = 'A'
        self._notes_button = ToolButton('notes')
        self._notes_button.set_tooltip(_('Notes'))
        self._notes_button.connect('clicked',
                                        self._button_selection_cb)
        self.insert(self._notes_button, -1)
        self._setup_notes_palette()

        self._octave = 4
        self._octaves_button = ToolButton('octaves')
        self._octaves_button.set_tooltip(_('Octaves'))
        self._octaves_button.connect('clicked',
                                        self._button_selection_cb)
        self.insert(self._octaves_button, -1)
        self._setup_octaves_palette()

        # The entry is used to display a note or for direct user input
        self._freq_entry = gtk.Entry()
        self._freq_entry.set_text('440')  # A
        self._freq_entry_changed_id = self._freq_entry.connect(
            'changed', self._update_freq_entry)
        if hasattr(self._freq_entry, 'set_tooltip_text'):
            self._freq_entry.set_tooltip_text(
                _('Enter a frequency to display.'))
        self._freq_entry.set_width_chars(8)
        self._freq_entry.show()
        toolitem = gtk.ToolItem()
        toolitem.add(self._freq_entry)
        self.insert(toolitem, -1)
        toolitem.show()

        self._new_tuning_line = ToolButton('tuning-tools')
        self._new_tuning_line.show()
        self.insert(self._new_tuning_line, -1)
        self._new_tuning_line.set_tooltip(_('Show tuning line.'))
        self._new_tuning_line.connect('clicked', self.tuning_line_cb)

        separator = gtk.SeparatorToolItem()
        separator.props.draw = True
        self.insert(separator, -1)

        self._harmonic = ToolButton('harmonics')
        self._harmonic.show()
        self.insert(self._harmonic, -1)
        self._harmonic.set_tooltip(_('Show harmonics.'))
        self._harmonic.connect('clicked', self.harmonic_cb)

        separator = gtk.SeparatorToolItem()
        separator.props.draw = True
        self.insert(separator, -1)

        self._play_tone = ToolButton('media-playback-start')
        self._play_tone.show()
        self.insert(self._play_tone, -1)
        self._play_tone.set_tooltip(_('Play a note.'))
        self._play_tone.connect('clicked', self.play_cb)

        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.insert(separator, -1)

        self.label = gtk.Label('')
        self.label.set_use_markup(True)
        self.label.show()
        toolitem = gtk.ToolItem()
        toolitem.add(self.label)
        self.insert(toolitem, -1)
        toolitem.show()

        self.show_all()

    def _update_note(self):
        ''' Calculate the frequency based on note and octave '''
        if not hasattr(self, '_freq_entry'):  # Still setting up toolbar
            return
        i = self._octave * 12 + NOTES.index(self._note)
        freq = A0 * pow(TWELTHROOT2, i)
        self._updating_note = True
        self._freq_entry.set_text('%0.3f' % (freq))
        self.label.set_markup(SPAN % (style.COLOR_WHITE.get_html(),
                                      self._note + str(self._octave)))
        if self._show_tuning_line:
            self.activity.wave.tuning_line = freq
        return

    def _update_freq_entry(self, widget):
        # Calculate a note from a frequency
        if not self._updating_note:  # Only if user types in a freq.
            try:
                freq = float(self._freq_entry.get_text())
                # Only consider notes in piano range
                if freq < A0 * 0.97:
                    self.label.set_text('< A0')
                    return
                if freq > C8 * 1.03:
                    self.label.set_text('> C8')
                    return
                self.label.set_markup(freq_note(freq, flatsharp=True))
            except ValueError:
                return

        self._updating_note = False

    def _button_selection_cb(self, widget):
        palette = widget.get_palette()
        if palette:
            if not palette.is_up():
                palette.popup(immediate=True, state=palette.SECONDARY)
            else:
                palette.popdown(immediate=True)
            return

    def _setup_notes_palette(self):
        self._notes_palette = self._notes_button.get_palette()

        for note in NOTES:
            menu_item = MenuItem(icon_name='',
                                 text_label=note)
            menu_item.connect('activate', self._note_selected_cb, note)
            self._notes_palette.menu.append(menu_item)
            menu_item.show()

    def _note_selected_cb(self, widget, note):
        self._note = note
        self._update_note()

    def _setup_octaves_palette(self):
        self._octaves_palette = self._octaves_button.get_palette()

        for octave in range(9):
            menu_item = MenuItem(icon_name='',
                                 text_label=str(octave))
            menu_item.connect('activate', self._octave_selected_cb, octave)
            self._octaves_palette.menu.append(menu_item)
            menu_item.show()

    def _octave_selected_cb(self, widget, octave):
        self._octave = octave
        self._update_note()

    def _setup_instrument_palette(self):
        self.instrument_palette = self._instrument_button.get_palette()

        self.instrument = []
        for k in INSTRUMENT_DICT.keys():
            self.instrument.append(k)
            menu_item = MenuItem(icon_name='',
                                 text_label=k)
            menu_item.connect('activate', self.instrument_selected_cb, k)
            self.instrument_palette.menu.append(menu_item)
            menu_item.show()

    def instrument_selected_cb(self, button, instrument):
        ''' Callback for instrument control '''
        logging.debug(instrument)
        if self._tuning_tool is not None:
            self.remove(self._tuning_tool)

        if instrument == _('None'):
            self.activity.wave.instrument = None

            # Remove any previous tuning button
            if hasattr(self, '_tuning_button'):
                self._tuning_button.destroy()

            # Restore the notes, octaves buttons
            if hasattr(self, '_notes_button'):
                self.insert(self._notes_button, 2)
                self.insert(self._octaves_button, 3)
            return

        self.remove(self._notes_button)
        self.remove(self._octaves_button)

        self.activity.wave.instrument = instrument

        # If we are not already in freq. base, switch.
        if not self.activity.wave.get_fft_mode():
            self.activity.timefreq_control()

        # Add a Tuning palette for this instrument
        self._tuning_button = ToolButton('notes')
        self._tuning_button.set_tooltip(instrument)
        self._tuning_button.connect('clicked', self._button_selection_cb)
        self.insert(self._tuning_button, 1)
        self._setup_tuning_palette(instrument)

    def _setup_tuning_palette(self, instrument):
        self._tuning_palette = self._tuning_button.get_palette()

        self.tuning = []
        self.tuning.append(_('All notes'))
        menu_item = MenuItem(icon_name='', text_label=_('All notes'))
        menu_item.connect('activate', self._tuning_selected_cb,
                          instrument, -1)
        self._tuning_palette.menu.append(menu_item)
        menu_item.show()

        for i, f in enumerate(INSTRUMENT_DICT[instrument]):
            self.tuning.append(freq_note(f))
            menu_item = MenuItem(icon_name='',
                                 text_label=freq_note(f))
            menu_item.connect('activate', self._tuning_selected_cb,
                              instrument, i)
            self._tuning_palette.menu.append(menu_item)
            menu_item.show()

        self.show_all()

    def _tuning_selected_cb(self, widget, instrument, fidx):
        ''' Update note '''
        if not hasattr(self, '_freq_entry'):  # Still setting up toolbar?
            return

        if not instrument in INSTRUMENT_DICT:
            return

        if fidx == -1:  # All notes
            self.activity.wave.instrument = instrument
            self.activity.wave.tuning_line = 0.0
            self._new_tuning_line.set_icon('tuning-tools')
            self._new_tuning_line.set_tooltip(_('Show tuning line.'))
            self._show_tuning_line = False
        else:
            freq = INSTRUMENT_DICT[instrument][fidx]
            self.activity.wave.instrument = None
            self.activity.wave.tuning_line = freq
            self._new_tuning_line.set_icon('tuning-tools-off')
            self._new_tuning_line.set_tooltip(_('Hide tuning line.'))
            self._show_tuning_line = True

        self._updating_note = False

    def harmonic_cb(self, *args):
        ''' Callback for harmonics control '''
        self.activity.wave.harmonics = not self.activity.wave.harmonics
        if self.activity.wave.harmonics:
            self._harmonic.set_icon('harmonics-off')
            self._harmonic.set_tooltip(_('Hide harmonics.'))
            if self.activity.wave.instrument is None and \
               self.activity.wave.tuning_line == 0.0:
                self._load_tuning_line()
        else:
            self._harmonic.set_icon('harmonics')
            self._harmonic.set_tooltip(_('Show harmonics.'))

    def tuning_line_cb(self, *args):
        ''' Callback for tuning insert '''
        if self._show_tuning_line:
            self.activity.wave.tuning_line = 0.0
            self._new_tuning_line.set_icon('tuning-tools')
            self._new_tuning_line.set_tooltip(_('Show tuning line.'))
            self._show_tuning_line = False
        else:
            self._load_tuning_line()

    def _load_tuning_line(self):
        ''' Read the freq entry and use value to set tuning line '''
        freq = self._freq_entry.get_text()
        try:
            self.activity.wave.tuning_line = float(freq)
            if freq < 0:
                freq = -freq
            self._new_tuning_line.set_icon('tuning-tools-off')
            self._new_tuning_line.set_tooltip(_('Hide tuning line.'))
            self._show_tuning_line = True
        except ValueError:
            self.activity.wave.tuning_line = 0.0
            self._freq_entry.set_text('0')
        # If we are not already in freq. base, switch.
        if not self.activity.wave.get_fft_mode():
            self.activity.timefreq_control()

    def play_cb(self, *args):
        ''' Save settings, turn off display, and then play a tone at
        the current frequency '''
        channels = []
        for c in range(self.activity.audiograb.channels):
            channels.append(self.activity.wave.get_visibility(channel=c))
            self.activity.wave.set_visibility(False, channel=c)
        wave_status = self.activity.wave.get_active()
        self.activity.wave.set_context_off()
        self.activity.wave.set_active(False)
        if self.activity.hw in [XO4, XO175]:
            self.activity.audiograb.stop_grabbing()

        freq = float(self._freq_entry.get_text())
        gobject.timeout_add(200, self.play_sound, freq, channels, wave_status)

    def play_sound(self, freq, channels, wave_status):
        ''' Play the sound and then restore wave settings '''
        self._play_sinewave(freq, 5000, 1)

        if self.activity.hw in [XO4, XO175]:
            self.activity.sensor_toolbar.set_mode('sound')
            self.activity.sensor_toolbar.set_sound_context()
            self.activity.audiograb.start_grabbing()
        for c in range(self.activity.audiograb.channels):
            self.activity.wave.set_visibility(channels[c], channel=c)
        self.activity.wave.set_context_on()
        self.activity.wave.set_active(wave_status)

    def _play_sinewave(self, pitch, amplitude=5000, duration=1):
        """ Create a Csound score to play a sine wave. """
        self.orchlines = []
        self.scorelines = []
        self.instrlist = []

        try:
            pitch = abs(float(pitch))
            amplitude = abs(float(amplitude))
            duration = abs(float(duration))
        except ValueError:
            logging.error('bad args to _play_sinewave')
            return

        self._prepare_sinewave(pitch, amplitude, duration)

        path = os.path.join(self.activity.get_activity_root(), 'instance',
                            'tmp.csd')
        # Create a csound file from the score.
        self._audio_write(path)

        # Play the csound file.
        output = check_output(['csound', path], 'call to csound failed?')
        # os.system('csound ' + path + ' > /dev/null 2>&1')

    def _prepare_sinewave(self, pitch, amplitude, duration, starttime=0,
                          pitch_envelope=99, amplitude_envelope=100,
                          instrument=1):

        pitenv = pitch_envelope
        ampenv = amplitude_envelope
        if not 1 in self.instrlist:
            self.orchlines.append("instr 1\n")
            self.orchlines.append("kpitenv oscil 1, 1/p3, p6\n")
            self.orchlines.append("aenv oscil 1, 1/p3, p7\n")
            self.orchlines.append("asig oscil p5*aenv, p4*kpitenv, p8\n")
            self.orchlines.append("out asig\n")
            self.orchlines.append("endin\n\n")
            self.instrlist.append(1)

        self.scorelines.append("i1 %s %s %s %s %s %s %s\n" %
                               (str(starttime), str(duration), str(pitch),
                                str(amplitude), str(pitenv), str(ampenv),
                                str(instrument)))

    def _audio_write(self, file):
        """ Compile a .csd file. """

        csd = open(file, "w")
        csd.write("<CsoundSynthesizer>\n\n")
        csd.write("<CsOptions>\n")
        csd.write("-+rtaudio=alsa -odevaudio -m0 -d -b256 -B512\n")
        csd.write("</CsOptions>\n\n")
        csd.write("<CsInstruments>\n\n")
        csd.write("sr=16000\n")
        csd.write("ksmps=50\n")
        csd.write("nchnls=1\n\n")
        for line in self.orchlines:
            csd.write(line)
        csd.write("\n</CsInstruments>\n\n")
        csd.write("<CsScore>\n\n")
        csd.write("f1 0 2048 10 1\n")
        csd.write("f2 0 2048 10 1 0 .33 0 .2 0 .143 0 .111\n")
        csd.write("f3 0 2048 10 1 .5 .33 .25 .2 .175 .143 .125 .111 .1\n")
        csd.write("f10 0 2048 10 1 0 0 .3 0 .2 0 0 .1\n")
        csd.write("f99 0 2048 7 1 2048 1\n")
        csd.write("f100 0 2048 7 0. 10 1. 1900 1. 132 0.\n")
        csd.write(self.scorelines.pop())
        csd.write("e\n")
        csd.write("\n</CsScore>\n")
        csd.write("\n</CsoundSynthesizer>")
        csd.close()


class InstrumentToolbar(gtk.Toolbar):
    ''' The toolbar for adding new instruments '''

    def __init__(self, activity):
        gtk.Toolbar.__init__(self)
        self.activity = activity
        self.new_instruments = []

        self._name_entry = gtk.Entry()
        self._name_entry.set_text(_('my instrument'))
        self._name_entry_changed_id = self._name_entry.connect(
            'changed', self.update_name_entry)
        if hasattr(self._name_entry, 'set_tooltip_text'):
            self._name_entry.set_tooltip_text(
                _('Enter instrument name.'))
        self._name_entry.set_width_chars(24)
        self._name_entry.show()
        toolitem = gtk.ToolItem()
        toolitem.add(self._name_entry)
        self.insert(toolitem, -1)
        toolitem.show()

        self._note = 'A'
        self._notes_button = ToolButton('notes')
        self._notes_button.set_tooltip(_('Notes'))
        self._notes_button.connect('clicked',
                                        self._button_selection_cb)
        self.insert(self._notes_button, -1)
        self._setup_notes_palette()
        self._notes_button.show()

        self._octave = 4
        self._octaves_button = ToolButton('octaves')
        self._octaves_button.set_tooltip(_('Octaves'))
        self._octaves_button.connect('clicked',
                                        self._button_selection_cb)
        self.insert(self._octaves_button, -1)
        self._setup_octaves_palette()
        self._octaves_button.show()

        self._new_note = ToolButton('list-add')
        self._new_note.show()
        self.insert(self._new_note, -1)
        self._new_note.set_tooltip(_('Add a new note.'))
        self._new_note.connect('clicked', self.new_note_cb)
        self._new_note.show()

    def _button_selection_cb(self, widget):
        palette = widget.get_palette()
        if palette:
            if not palette.is_up():
                palette.popup(immediate=True, state=palette.SECONDARY)
            else:
                palette.popdown(immediate=True)
            return

    def _setup_notes_palette(self):
        self._notes_palette = self._notes_button.get_palette()

        for note in NOTES:
            menu_item = MenuItem(icon_name='',
                                 text_label=note)
            menu_item.connect('activate', self._note_selected_cb, note)
            self._notes_palette.menu.append(menu_item)
            menu_item.show()

    def _note_selected_cb(self, widget, note):
        self._note = note

    def _setup_octaves_palette(self):
        self._octaves_palette = self._octaves_button.get_palette()

        for octave in range(9):
            menu_item = MenuItem(icon_name='',
                                 text_label=str(octave))
            menu_item.connect('activate', self._octave_selected_cb, octave)
            self._octaves_palette.menu.append(menu_item)
            menu_item.show()

    def _octave_selected_cb(self, widget, octave):
        self._octave = octave

    def update_name_entry(self, *args):
        ''' Add name to INSTRUMENT_DICT and combo box '''
        # Wait until a note has been added...
        return

    def new_note_cb(self, *args):
        ''' Add a new note to instrument tuning list '''
        name = self._name_entry.get_text()
        if name not in INSTRUMENT_DICT:
            INSTRUMENT_DICT[name] = []
            self.activity.tuning_toolbar.instrument.append(name)
            i = len(self.activity.tuning_toolbar.instrument)
            menu_item = MenuItem(icon_name='',
                                 text_label=name)
            menu_item.connect(
                'activate',
                self.activity.tuning_toolbar.instrument_selected_cb,
                name)
            self.activity.tuning_toolbar.instrument_palette.menu.append(
                menu_item)
            menu_item.show()
            self.new_instruments.append(name)

        freq = A0 * pow(TWELTHROOT2,
                        self._octave * 12 + NOTES.index(self._note))
        if freq not in INSTRUMENT_DICT[name]:
            INSTRUMENT_DICT[name].append(freq)


def note_octave(note, octave):
    if '/' in note:
        flat, sharp = note.split('/')
        return '%s%d/%s%d' % (flat, octave, sharp, octave)
    else:
        return '%s%d' % (note, octave)


def freq_note(freq, flatsharp=False):
    if flatsharp:  # calculate if we are sharp or flat
        for i in range(88):
            f = A0 * pow(TWELTHROOT2, i)
            if freq < f * 1.03 and freq > f * 0.97:
                label = NOTES[i % 12] + str(int(i / 12))
                if freq < f * 0.98:
                    label = '%s %s %s' % (FLAT, label, FLAT)
                    return SPAN % (COLOR_RED.get_html(), label)
                elif freq < f * 0.99:
                    label = '%s %s %s' % (FLAT, label, FLAT)
                    return SPAN % (COLOR_YELLOW.get_html(), label)
                elif freq > f * 1.02:
                    label = '%s %s %s' % (SHARP, label, SHARP)
                    return SPAN % (COLOR_RED.get_html(), label)
                elif freq > f * 1.01:
                    label = '%s %s %s' % (SHARP, label, SHARP)
                    return SPAN % (COLOR_YELLOW.get_html(), label)
                else:
                    return SPAN % (style.COLOR_WHITE.get_html(), label)
    else:
        for i in range(88):
            f = A0 * pow(TWELTHROOT2, i)
            if freq < f * 1.03 and freq > f * 0.97:  # Found a match
                return note_octave(NOTES[i % 12], int(i / 12))
        return '?'


def freq_index(freq):
    for i in range(88):
        f = A0 * pow(TWELTHROOT2, i)
        if freq < f * 1.03 and freq > f * 0.97:  # Found a match
            return i
    return 0


def index_to_octave(i):
    return int((i - 3) / 12) + 1  # -3 because we start with A


def index_to_note(i):
    return (i - 3) % 12  # -3 because we start with A
