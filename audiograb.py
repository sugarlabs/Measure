#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, OLPC
#    
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
import gst
import gobject
import os
import subprocess
from struct import unpack
from string import find
import config 		#This has all the golabals


class AudioGrab():


    def __init__(self, callable1, journal):

        self.callable1 = callable1
        self.ji = journal

        self.temp_buffer = []
        self.picture_buffer = []

        self.draw_graph_status = False
        self.f = None
        self.logging_status = False
        self.screenshot = True

        self.rate = 48000		
        self.final_count = 0
        self.count_temp = 0
        self.entry_count = 0


        self.waveform_id = 1
        self.logging_state = False
        self.buffer_interval_logging = 0
        self.counter_buffer = 0

        ####Variables for saving and resuming state of sound device######
        self.master  = self.get_master()
        self.PCM = self.get_PCM_gain()
        self.mic = self.get_mic_gain()
        self.bias = config.BIAS
        self.dcmode =  config.DC_MODE_ENABLE
        self.capture_gain  = config.CAPTURE_GAIN
        self.mic_boost = config.MIC_BOOST
        #################################################################


        self.pipeline = gst.Pipeline("pipeline")
        self.alsasrc = gst.element_factory_make("alsasrc", "alsa-source")
        self.pipeline.add(self.alsasrc)
        self.caps1 = gst.element_factory_make("capsfilter", "caps1")
        self.pipeline.add(self.caps1)
        caps_str = "audio/x-raw-int,rate=%d,channels=1,depth=16" % (config.RATE, )
        self.caps1.set_property("caps", gst.caps_from_string(caps_str) )
        self.fakesink = gst.element_factory_make("fakesink", "fsink")
        self.pipeline.add(self.fakesink)		
        self.fakesink.connect("handoff", self.on_buffer)	
        self.fakesink.set_property("signal-handoffs",True) 
        gst.element_link_many(self.alsasrc, self.caps1, self.fakesink)


        self.dont_queue_the_buffer = False


    def set_handoff_signal(self, handoff_state):
        """Sets whether the handoff signal would generate an interrupt or not"""
        self.fakesink.set_property("signal-handoffs",handoff_state)

    def _new_buffer(self,buf):
        if self.dont_queue_the_buffer == False:
            self.callable1(str(buf))
            #print "$$audiograb:have just called callback to update buffer for drawing"
        else:
            pass
            #print "$$audiograb:not queuing2"
            


    def on_buffer(self, element, buffer, pad):		
        """The function that is called whenever new data is available
        This is the signal handler for the handoff signal"""
        self.temp_buffer = buffer
        if self.dont_queue_the_buffer == False:
            gobject.timeout_add(config.AUDIO_BUFFER_TIMEOUT, self._new_buffer, self.temp_buffer)
        else:
            pass

        if self.logging_state==True:
            if self.waveform_id == config.SOUND_MAX_WAVE_LOGS:
                self.waveform_id = 1
                self.logging_state = False
                self.ji.stop_session()
            else:
                if self.counter_buffer == self.buffer_interval_logging:
                    #gobject.timeout_add(300, self._emit_for_logging, self.temp_buffer)
                    self._emit_for_logging(str(self.temp_buffer))
                    self.counter_buffer=0

                self.counter_buffer+=1

            if self.buffer_interval_logging ==0:        #If a record is to be written, thats all for the logging session
                self.logging_state = False
                self.ji.stop_session()
                self.waveform_id = 1

        return False


    def set_freeze_the_display(self, freeze = False):
        """Useful when just the display is needed to be frozen, but logging should continue"""
        self.dont_queue_the_buffer = not freeze


    def get_freeze_the_display(self):
        """Returns state of queueing the buffer"""
        return not self.dont_queue_the_buffer

    def _emit_for_logging(self, buf):
        """Sends the data for logging"""
        if self.buffer_interval_logging==0:
            #self.ji.write_record(self.picture_buffer)
            self.ji.take_screenshot()
        else:
            if self.screenshot == True:
                self.ji.take_screenshot(self.waveform_id)
                self.waveform_id+=1
            else:
                temp_buf = list(unpack( str(int(len(buf))/2)+'h' , buf))
                self.ji.write_value(temp_buf[0])


    def start_sound_device(self):
        """Start or Restart grabbing data from the audio capture"""
        gst.event_new_flush_start()
        self.pipeline.set_state(gst.STATE_PLAYING)


    def stop_sound_device(self):
        """Stop grabbing data from capture device"""
        gst.event_new_flush_stop()
        self.pipeline.set_state(gst.STATE_NULL)


    def save_state(self):
        """Saves the state of all audio controls"""
        self.master = self.get_master()
        self.PCM = self.get_PCM_gain()
        self.mic = self.get_mic_gain()
        self.bias = self.get_bias()
        self.dcmode =  self.get_dc_mode()
        self.capture_gain  = self.get_capture_gain()
        self.mic_boost = self.get_mic_boost()

    def resume_state(self):
        """Put back all audio control settings from the saved state"""
        self.set_master(self.master)
        self.set_PCM_gain(self.PCM )
        self.set_mic_gain(self.mic)
        self.set_bias(self.bias)
        self.set_dc_mode(self.dcmode)
        self.set_capture_gain(self.capture_gain)
        self.set_mic_boost(self.mic_boost)


    def set_logging_params(self, start_stop=False, interval=0, screenshot = True):
        """Configures for logging of data i.e. starts or stops a session
        Sets an interval if logging interval is to be started
        Sets if screenshot of waveform is to be taken or values need to be written"""
        self.logging_state = start_stop 
        self.set_buffer_interval_logging(interval)
        #if interval==0:
	    #    self.take_picture()
        self.reset_counter_buffer()
        self.screenshot = screenshot

    def take_picture(self):
        """Used to grab and temporarily store the current buffer"""
        self.picture_buffer = list(unpack( str(int(len(str(self.temp_buffer)))/2)+'h' , str(self.temp_buffer)))

    def set_logging_state(self, start_stop=False):
        """Sets whether buffer is to be emited for logging (True) or not (False)"""
        self.logging_state = start_stop

    def set_buffer_interval_logging(self, interval=0):
        """Sets the number of buffers after which a buffer needs to be emitted"""
        self.buffer_interval_logging = interval

    def reset_counter_buffer(self):
        """Resets the counter buffer used to keep track of after how many buffers to emit a buffer for logging"""
        self.counter_buffer = 0


    def mute_master(self):
        """Mutes the Master Control"""
        os.system("amixer set Master mute")

    def unmute_master(self):
        """Unmutes the Master Control"""
        os.system("amixer set Master unmute")

    def mute_PCM(self):
        """Mutes the PCM Control"""
        os.system("amixer set PCM mute")

    def unmute_PCM(self):
        """Unmutes the PCM Control"""
        os.system("amixer set PCM unmute")

    def mute_mic(self):
        """Mutes the Mic Control"""
        os.system("amixer set Mic mute")

    def unmute_mic(self):
        """Unmutes the Mic Control"""
        os.system("amixer set Mic unmute")

    def set_master(self, master_val ):
        """Sets the Master gain slider settings 
        master_val must be given as an integer between 0 and 100 indicating the
        percentage of the slider to be set"""
        os.system("amixer set Master " + str(master_val) + "%")


    def get_master(self):
        """Gets the Master gain slider settings. The value returned is an integer between 0-100
        and is an indicative of the percentage 0 - 100%"""
        p = str(subprocess.Popen(["amixer", "get", "Master"], stdout=subprocess.PIPE).communicate()[0])
        p = p[find(p,"Front Left:"):]
        p = p[find(p,"[")+1:]
        p = p[:find(p,"%]")]
        return int(p)



    def get_mix_for_recording(self):
        """Returns True if Mix is set as recording device and False if it isn't """
        p = str(subprocess.Popen(["amixer", "get", "Mix", "capture", "cap"], stdout=subprocess.PIPE).communicate()[0])
        p = p[find(p,"Mono:"):]
        p = p[find(p,"[")+1:]
        p = p[:find(p,"]")]
        if p=="on" :
	        return True
        else:
	        return False
	

    def get_mic_for_recording(self):
        """Returns True if mic is set as recording device and False if it isn't """
        p = str(subprocess.Popen(["amixer", "get", "Mic", "capture", "cap"], stdout=subprocess.PIPE).communicate()[0])
        p = p[find(p,"Mono:"):]
        p = p[find(p,"[")+1:]
        p = p[:find(p,"]")]
        if p=="on" :
	        return True
        else:
	        return False

    def set_mic_for_recording(self):
        """Sets Mic as the default recording source"""
        os.system("amixer set Mic capture cap")

    def set_mix_for_recording(self):
        """Sets Mix as the default recording source"""
        os.system("amixer set Mix capture cap")


    def set_bias(self,bias_state=False):
        """Sets the Bias control
        pass False to disable and True to enable"""
        if bias_state==False:
	        bias_str="mute"
        else:
	        bias_str="unmute"
        os.system("amixer set 'V_REFOUT Enable' " + bias_str)

    def get_bias(self):
        """Returns the setting of Bias control 
        i.e. True: Enabled and False: Disabled"""
        p = str(subprocess.Popen(["amixer", "get", "'V_REFOUT Enable'"], stdout=subprocess.PIPE).communicate()[0])
        p = p[find(p,"Mono:"):]
        p = p[find(p,"[")+1:]
        p = p[:find(p,"]")]
        if p=="on" :
	        return True
        else:
	        return False

    def set_dc_mode(self, dc_mode = False):
        """Sets the DC Mode Enable control
        pass False to mute and True to unmute"""
        if dc_mode==False:
	        dcm_str="mute"
        else:
	        dcm_str="unmute"
        os.system("amixer set 'DC Mode Enable' " + dcm_str)

    def get_dc_mode(self):
        """Returns the setting of DC Mode Enable control 
        i .e. True: Unmuted and False: Muted"""
        p = str(subprocess.Popen(["amixer", "get", "'DC Mode Enable'"], stdout=subprocess.PIPE).communicate()[0])
        p = p[find(p,"Mono:"):]
        p = p[find(p,"[")+1:]
        p = p[:find(p,"]")]
        if p=="on" :
	        return True
        else:
	        return False

    def set_mic_boost(self, mic_boost=False):
        """Sets the Mic Boost +20dB control
        pass False to mute and True to unmute"""
        if mic_boost==False:
	        mb_str="mute"
        else:
	        mb_str="unmute"
        os.system("amixer set 'Mic Boost (+20dB)' " + mb_str)

    def get_mic_boost(self):
        """Returns the setting of Mic Boost +20dB control 
        i.e. True: Unmuted and False: Muted"""
        p = str(subprocess.Popen(["amixer", "get", "'Mic Boost (+20dB)'"], stdout=subprocess.PIPE).communicate()[0])
        p = p[find(p,"Mono:"):]
        p = p[find(p,"[")+1:]
        p = p[:find(p,"]")]
        if p=="on" :
	        return True
        else:
	        return False
	

    def set_capture_gain(self, capture_val):
        """Sets the Capture gain slider settings 
        capture_val must be given as an integer between 0 and 100 indicating the
        percentage of the slider to be set"""
        os.system("amixer set Capture " + str(capture_val) + "%")


    def get_capture_gain(self):
        """Gets the Capture gain slider settings. The value returned is an integer between 0-100
        and is an indicative of the percentage 0 - 100%"""
        p = str(subprocess.Popen(["amixer", "get", "Capture"], stdout=subprocess.PIPE).communicate()[0])
        p = p[find(p,"Front Left:"):]
        p = p[find(p,"[")+1:]
        p = p[:find(p,"%]")]
        return int(p)


    def set_PCM_gain(self, PCM_val):
        """Sets the PCM gain slider settings 
        PCM_val must be given as an integer between 0 and 100 indicating the
        percentage of the slider to be set"""
        os.system("amixer set PCM " + str(PCM_val) + "%")

    def get_PCM_gain(self):
        """Gets the PCM gain slider settings. The value returned is an indicative of the percentage 0 - 100%"""
        p = str(subprocess.Popen(["amixer", "get", "PCM"], stdout=subprocess.PIPE).communicate()[0])
        p = p[find(p,"Front Left:"):]
        p = p[find(p,"[")+1:]
        p = p[:find(p,"%]")]
        return int(p)


    def set_mic_gain(self, mic_val):
        """Sets the MIC gain slider settings 
        mic_val must be given as an integer between 0 and 100 indicating the
        percentage of the slider to be set"""
        os.system("amixer set Mic " + str(mic_val) + "%")

    def get_mic_gain(self):
        """Gets the MIC gain slider settings. The value returned is an indicative of the percentage 0 - 100%"""
        p = str(subprocess.Popen(["amixer", "get", "Mic"], stdout=subprocess.PIPE).communicate()[0])
        p = p[find(p,"Mono:"):]
        p = p[find(p,"[")+1:]
        p = p[:find(p,"%]")]
        try:
            return int(p)
        except:
            # in case alsamixer doesn't report a percentage
            return 0

    def set_sampling_rate(self, sr):
        """Sets the sampling rate of the capture device
        Sampling rate must be given as an integer for example 16000 for setting 16Khz sampling rate
        The sampling rate would be set in the device to the nearest available"""
        self.pause_grabbing()
        caps_str = "audio/x-raw-int,rate=%d,channels=1,depth=16" % (sr, )
        self.caps1.set_property("caps", gst.caps_from_string(caps_str) )
        self.resume_grabbing()


    def get_sampling_rate(self):
        """Gets the sampling rate of the capture device"""
        return int(self.caps1.get_property("caps")[0]['rate'] )


    def set_callable1(self, callable1):
        """Sets the callable to the drawing function for giving the
        data at the end of idle-add"""
        self.callable1 = callable1


    def set_sensor_type(self, sensor_type=1):
        """Set the type of sensor you want to use. Set sensor_type according to the following
        0 - AC coupling with Bias Off --> Very rarely used. Use when connecting a dynamic microphone externally
        1 - AC coupling with Bias On --> The default settings. The internal MIC uses these
        2 - DC coupling with Bias Off --> Used when using a voltage output sensor. For example LM35 which gives output proportional to temperature
        3 - DC coupling with Bias On --> Used with resistive sensors. For example"""
        if sensor_type==0:
	        self.set_dc_mode(False)
	        self.set_bias(False)
	        self.set_capture_gain(50)
	        self.set_mic_boost(True)
        elif sensor_type==1:
	        self.set_dc_mode(False)
	        self.set_bias(True)
	        self.set_capture_gain(40)
	        self.set_mic_boost(True)
        elif sensor_type==2:
	        self.set_dc_mode(True)
	        self.set_bias(False)
	        self.set_capture_gain(0)
	        self.set_mic_boost(False)
        elif sensor_type==3:
	        self.set_dc_mode(True)
	        self.set_bias(True)
	        self.set_capture_gain(0)
	        self.set_mic_boost(False)


    def start_grabbing(self):
        """Called right at the start of the Activity"""
        self.start_sound_device()
        #self.set_handoff_signal(True)
        ####Sound device settings at start####
        #self.set_sampling_rate(config.RATE)
        #self.set_mic_boost(config.MIC_BOOST)
        #self.set_dc_mode(config.DC_MODE_ENABLE)
        #self.set_capture_gain(config.CAPTURE_GAIN)
        #self.set_bias(config.BIAS)
        ######################################



    def pause_grabbing(self):
        """When Activity goes into background"""
        self.save_state()
        self.stop_sound_device()

    def resume_grabbing(self):
        """When Activity becomes active after going to background"""
        self.start_sound_device()
        self.resume_state()
   

    def stop_grabbing(self):
        self.stop_sound_device()
        self.set_handoff_signal(False)

    def on_activity_quit(self):
        """When Activity quits"""
        self.set_mic_boost(config.QUIT_MIC_BOOST)
        self.set_dc_mode(config.QUIT_DC_MODE_ENABLE)
        self.set_capture_gain(config.QUIT_CAPTURE_GAIN)
        self.set_bias(config.QUIT_BIAS)
        self.set_PCM_gain(config.QUIT_PCM)
        self.stop_sound_device()





