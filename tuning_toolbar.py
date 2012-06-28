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

import gtk
import gobject
import subprocess
from gettext import gettext as _

from config import ICONS_DIR, CAPTURE_GAIN, MIC_BOOST, XO1, XO15, XO175, XO30,\
    INSTRUMENT_DICT

from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.combobox import ComboBox
from sugar.graphics.toolcombobox import ToolComboBox
from sugar.graphics import style
import logging
log = logging.getLogger('measure-activity')
log.setLevel(logging.DEBUG)


NOTES = ['C', 'C♯/D♭', 'D', 'D♯/E♭', 'E', 'F', 'F♯/G♭', 'G', 'G♯/A♭', 'A',
         'A♯/B♭', 'B']
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

        # Set up Instrument Combo box
        self.instrument_combo = ComboBox()
        self.instrument = [_('None')]
        for k in INSTRUMENT_DICT.keys():
            self.instrument.append(k)
        self._instrument_changed_id = self.instrument_combo.connect(
            'changed', self.update_instrument_control)
        for i, instrument in enumerate(self.instrument):
            self.instrument_combo.append_item(i, instrument, None)
        self.instrument_combo.set_active(0)
        if hasattr(self.instrument_combo, 'set_tooltip_text'):
            self.instrument_combo.set_tooltip_text(_('Tune an instrument.'))
        self._instrument_tool = ToolComboBox(self.instrument_combo)
        self.insert(self._instrument_tool, -1)

        if self.activity.has_toolbarbox:
            separator = gtk.SeparatorToolItem()
            separator.props.draw = True
            self.insert(separator, -1)

        self._notes_combo = ComboBox()
        n = 0
        for octave in range(9):
            for i in range(len(NOTES)):
                if octave == 0 and i < 9:  # Start with A0
                    continue
                self._notes_combo.append_item(
                    n, note_octave(i, octave), None)
                n += 1
        self._notes_combo.set_active(48)  # A4
        self._notes_changed_id = self._notes_combo.connect(
            'changed', self.update_note)
        if hasattr(self._notes_combo, 'set_tooltip_text'):
            self._notes_combo.set_tooltip_text(_('Notes'))
        self._notes_tool = ToolComboBox(self._notes_combo)
        self.insert(self._notes_tool, -1)

        # The entry is used to display a note or for direct user input
        self._freq_entry = gtk.Entry()
        self._freq_entry.set_text('440')  # A
        self._freq_entry_changed_id = self._freq_entry.connect(
            'changed', self.update_freq_entry)
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

        if self.activity.has_toolbarbox:
            separator = gtk.SeparatorToolItem()
            separator.props.draw = True
            self.insert(separator, -1)

        self._harmonic = ToolButton('harmonics')
        self._harmonic.show()
        self.insert(self._harmonic, -1)
        self._harmonic.set_tooltip(_('Show harmonics.'))
        self._harmonic.connect('clicked', self.harmonic_cb)

        if self.activity.has_toolbarbox:
            separator = gtk.SeparatorToolItem()
            separator.props.draw = True
            self.insert(separator, -1)

        self._play_tone = ToolButton('media-playback-start')
        self._play_tone.show()
        self.insert(self._play_tone, -1)
        self._play_tone.set_tooltip(_('Play a note.'))
        self._play_tone.connect('clicked', self.play_cb)

        if self.activity.has_toolbarbox:
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

    def update_note(self, *args):
        ''' Calculate the frequency based on note combo '''
        if not hasattr(self, '_freq_entry'):  # Still setting up toolbar
            return
        i = self._notes_combo.get_active()
        freq = A0 * pow(TWELTHROOT2, i)
        self._updating_note = True
        self._freq_entry.set_text('%0.3f' % (freq))
        self.label.set_markup(SPAN % (style.COLOR_WHITE.get_html(),
                                      note_octave(index_to_note(i),
                                                  index_to_octave(i))))
        if self._show_tuning_line:
            self.activity.wave.tuning_line = freq
        return

    def update_tuning_control(self, *args):
        ''' Update note '''
        if not hasattr(self, '_freq_entry'):  # Still setting up toolbar?
            return
        instrument = self.instrument[self.instrument_combo.get_active()]
        if not instrument in INSTRUMENT_DICT:
            return
        if self.tuning[self._tuning_combo.get_active()] == _('All notes'):
            self._notes_combo.set_active(
                freq_index(INSTRUMENT_DICT[instrument][0]))
            self.activity.wave.instrument = instrument
            self.activity.wave.tuning_line = 0.0
            self._new_tuning_line.set_icon('tuning-tools')
            self._new_tuning_line.set_tooltip(_('Show tuning line.'))
            self._show_tuning_line = False
        else:
            freq = INSTRUMENT_DICT[instrument][
                self._tuning_combo.get_active() - 1]  # All notes is 0
            self._notes_combo.set_active(
                freq_index(INSTRUMENT_DICT[instrument][
                        self._tuning_combo.get_active() - 1]))
            self.activity.wave.instrument = None
            self.activity.wave.tuning_line = freq
            self._new_tuning_line.set_icon('tuning-tools-off')
            self._new_tuning_line.set_tooltip(_('Hide tuning line.'))
            self._show_tuning_line = True
        self._updating_note = False

    def update_freq_entry(self, *args):
        # Calcualte a note from a frequency
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

    def update_instrument_control(self, *args):
        ''' Callback for instrument control '''
        instrument = self.instrument[self.instrument_combo.get_active()]
        if self._tuning_tool is not None:
            self.remove(self._tuning_tool)
        if instrument == _('None'):
            self.activity.wave.instrument = None
            if hasattr(self, '_notes_tool'):
                self.insert(self._notes_tool, 2)
            return
        self.remove(self._notes_tool)
        self.activity.wave.instrument = instrument
        # If we are not already in freq. base, switch.
        if not self.activity.wave.get_fft_mode():
            self.activity.timefreq_control()
        # Add a Tuning Combo box for this instrument
        self._tuning_combo = ComboBox()
        self.tuning = [_('All notes')]
        for f in INSTRUMENT_DICT[instrument]:
            self.tuning.append(freq_note(f))
        self._tuning_changed_id = self._tuning_combo.connect(
            'changed', self.update_tuning_control)
        for i, s in enumerate(self.tuning):
            self._tuning_combo.append_item(i, s, None)
        self._tuning_combo.set_active(0)
        if hasattr(self._tuning_combo, 'set_tooltip_text'):
            self._tuning_combo.set_tooltip_text(instrument)
        self._tuning_tool = ToolComboBox(self._tuning_combo)
        self.insert(self._tuning_tool, 1)
        self._tuning_combo.show()
        self._tuning_tool.show()
        self.show_all()

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
        freq = float(self._freq_entry.get_text())
        channels = []
        for c in range(self.activity.audiograb.channels):
            channels.append(self.activity.wave.get_visibility(channel=c))
            self.activity.wave.set_visibility(False, channel=c)
        wave_status = self.activity.wave.get_active()
        self.activity.wave.set_context_off()
        self.activity.wave.set_active(False)
        gobject.timeout_add(200, self.play_sound, freq, channels, wave_status)

    def play_sound(self, freq, channels, wave_status):
        ''' Play the sound and then restore wave settings '''
        if hasattr(subprocess, 'check_output'):
            try:
                output = subprocess.check_output(
                    ['speaker-test', '-t', 'sine', '-l', '1', '-f', '%f' % (
                            freq)])
            except subprocess.CalledProcessError:
                log.warning('call to speaker-test failed?')
        else:
            import commands
            (status, output) = commands.getstatusoutput(
                'speaker-test -t sine -l 1 -f %f' % (freq))
            if status != 0:
                log.warning('call to speaker-test failed?')
        for c in range(self.activity.audiograb.channels):
            self.activity.wave.set_visibility(channels[c], channel=c)
        self.activity.wave.set_context_on()
        self.activity.wave.set_active(wave_status)


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

        self._notes_combo = ComboBox()
        n = 0
        for octave in range(9):
            for i in range(len(NOTES)):
                if octave == 0 and i < 9:  # Start with A0
                    continue
                self._notes_combo.append_item(
                    n, note_octave(i, octave), None)
                n += 1
        self._notes_combo.set_active(48)  # A4
        if hasattr(self._notes_combo, 'set_tooltip_text'):
            self._notes_combo.set_tooltip_text(_('Notes'))
        self._notes_tool = ToolComboBox(self._notes_combo)
        self.insert(self._notes_tool, -1)
        self._notes_tool.show()

        self._new_note = ToolButton('list-add')
        self._new_note.show()
        self.insert(self._new_note, -1)
        self._new_note.set_tooltip(_('Add a new note.'))
        self._new_note.connect('clicked', self.new_note_cb)

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
            self.activity.tuning_toolbar.instrument_combo.append_item(
                i, name, None)
            self.new_instruments.append(name)
        i = self._notes_combo.get_active()
        freq = A0 * pow(TWELTHROOT2, i)
        if freq not in INSTRUMENT_DICT[name]:
            INSTRUMENT_DICT[name].append(freq)


def note_octave(note, octave):
    if '/' in NOTES[note]:
        flat, sharp = NOTES[note].split('/')
        return '%s%d/%s%d' % (flat, octave, sharp, octave)
    else:
        return '%s%d' % (NOTES[note], octave)


def freq_note(freq, flatsharp=False):
    if flatsharp:  # calculate if we are sharp or flat
        for i in range(88):
            f = A0 * pow(TWELTHROOT2, i)
            if freq < f * 1.03 and freq > f * 0.97:
                label = NOTES[index_to_note(i)]
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
                return note_octave(index_to_note(i), index_to_octave(i))
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
