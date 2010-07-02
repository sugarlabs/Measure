#! /usr/bin/python
#
#    Author:  Arjun Sarwal   arjun@laptop.org
#    Copyright (C) 2007, Arjun Sarwal
#    Copyright (C) 2009, Walter Bender
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

"""
journal.py 

Start_new_session(user="", Xscale=0, Yscale=0) or
continue_existing_session(session_id_to_continue=-1): must be called
before every logging session for logging value by value, use
write_value(value=0),for logging a whole set of values into one
session at one time, use write_record(value_set=[]) Note: session_id's
are unique within one instance of an Activity and are not re-assigned
even if one or more logging sessions are deleted
"""

#
# TODO: Clean up this mess
#


import csv
import os
import gtk
import dbus

from tempfile import mkstemp
from os import environ
from os.path import join
from numpy import array
from gettext import gettext as _

from sugar.datastore import datastore

# Initialize logging.
import logging
log = logging.getLogger('Measure')
log.setLevel(logging.DEBUG)
logging.basicConfig()

class JournalInteraction():
    """ Handles all of the data I/O with the Journal """
    def __init__(self, activity):
        """_jobject is the Journal object exiting denotes if a file exists with
        that journal object (resumed from journal) or not (started afresh)"""

        self.activity = activity
        self.session_id = 0
        self.num_rows=0
        self.logginginterval_status = ' '
        self.writer1 = None
        self.writer2 = None
        self.making_row = False
        self.temp_buffer = []
        self.append_existing = False
        self._stopped = True
        self.session_id_to_continue = 0
        
        self.jobject = None
   
        self.user = ""
        self.Xscale = 0
        self.Yscale = 0
        
        if self.activity.existing:
            try:
                self.set_max_session_id()
                self.set_number_of_rows()
            except:
                log.error("Couldn't get session id or rows")

        # log.debug("$$journal.py: This is the file I will work on" +\
        #    self.activity._jobject.file_path)
    
    def __del__(self):
        pass

    def on_quit(self):
        pass            
    
    def set_max_session_id(self):
        """Sets the existing maximum session_id if the file already exists"""
        self.session_id = self.get_number_of_records();

    def set_number_of_rows(self):
        """Sets the number of rows an existing file has"""
        reader = csv.reader(open(self.activity._jobject.file_path, "rb"))
        for row in reader:
            self.num_rows+=1

    def set_session_params(self, user="", Xscale=0, Yscale=0):
        self.user = user
        self.Xscale = Xscale
        self.Yscale = Yscale
    
    def start_new_session(self, user="", Xscale=0, Yscale=0, \
                          logginginterval_status=' ' ):
        """This needs to be called before starting any logging session"""
        self.user = user
        self.Xscale = Xscale
        self.Yscale = Yscale
        self.logginginterval_status = logginginterval_status
        self.session_id+=1
        self.num_rows+=1
        self.append_existing=False
        self.making_row=False
        # log.debug("$$journal.py: a new session has started; the session_id is"\
        #      + str(self.session_id))
        return self.session_id

    def continue_existing_session(self, session_id_to_continue=-1):
        """Must be called before attempting to continue any logging session"""
        self.append_existing=True
        self.session_id_to_continue=session_id_to_continue
        self.making_row=True

    def write_value(self, value=0):
        """Append the value passed to temp_buffer if a logging session is
        started and continuted If a previous logging session is to be
        continued upon, read the corresponding row from the file and continue
        to append it and then rewrite the whole row"""
        if self.append_existing:
            self.apppend_session(self.session_id_to_continue)
            self.append_existing=False
            
        if not self.making_row:
          #     self.write_session_params()
                self.temp_buffer.append(value)
                self.making_row = True
        else:   
            self.temp_buffer.append(value)
        self._stopped = False
        # log.debug("%s %s" % ("$$Journal.py: I just wrote this value", str(value)))

    def get_record(self, session_id=0):
        """Return list of values from logging session specified by session_id"""
        reader = csv.reader(open(self.activity._jobject.file_path, "rb"))
        for row in reader:
            if int(row[0])==session_id:
                temp =row
        for i in range(0,len(temp)):
            if i!=1:
                temp[i]=int(temp[i])
        return temp

    def get_number_of_records(self):
        """Returns the of records"""
        reader = csv.reader(open(self.activity._jobject.file_path, "rb"))
        count=0
        for row in reader:
            count+=1
        return count

    def stop_session(self):
        """Write the temp_buffer onto a file"""
        if self._stopped == False:
            if self.activity.existing:
                writer1 = csv.writer(open(self.activity._jobject.file_path,
                                          "ab"))
            else:
                writer1 = csv.writer(open(self.activity._jobject.file_path,
                                          "wb"))
                self.activity.existing =  True
	    for datum in self.temp_buffer:
		writer1.writerow( [ datum ] )
            del writer1
            self.temp_buffer = []
            self.making_row = False
            self.append_existing = False
	    try:
                self.jobject = datastore.create()
                try:
                    self.jobject.metadata['title'] = "%s %s" %\
                        (_("Measure Log"), str(self.logginginterval_status))
                    self.jobject.metadata['keep'] = '0'
                    self.jobject.metadata['buddies'] = ''
                    self.jobject.metadata['preview'] = ''
                    self.jobject.metadata['icon-color'] = \
                        self.activity.icon_colors
                    self.jobject.metadata['mime_type'] = 'text/csv'
                    self.jobject.file_path = self.activity._jobject.file_path
                    datastore.write(self.jobject)
                finally:
                    pass
            finally:
                log.debug("$$$ in outermost finally!!")
            self._stopped = True
    
    def get_number_of_cols(self):
        """Returns the maximum number of columns amongst all the data"""
        max = 0
        reader = csv.reader(open(self.activity._jobject.file_path, "rb"))
        for row in reader:
            if len(row)>max:
                max=len(row)
        return max
    
    def write_record(self, values=[]):
        """Write a complete row specified by values
        If file doesn't exist, open a new file and write to it"""
     #   self.write_session_params()
        self.temp_buffer+=values
        self.stop_session()
        self._stopped = False
        log.debug("$$journal.py: Wrote record: " + str(values))
    
    def write_session_params(self):
        """Write the session parameters to temp_buffers"""
        self.num_rows+=1
        self.temp_buffer.append("%s: %s" % (_('Session'), str(self.session_id)))
        self.temp_buffer.append("%s: %s" % (_('User'), str(self.user)))
        self.temp_buffer.append("%s: %s" % (_('Interval'),
                                           str(self.logginginterval_status)))
        ##TODO: Probably need to add a field for timing interval
        #self.temp_buffer.append(self.Xscale)
        #self.temp_buffer.append(self.Yscale)
    
    def get_session_params(self, session_id=-1):
        """TODO write this function"""
        pass

    def find_record(self, session_id=-1):
        """Returns the index 0 to N-1 of the record
        session_id may be shifted around due to deletion and editing
        returns -1 i it doesn't find it"""
        reader = csv.reader(open(self.activity._jobject.file_path, "rb"))
        found=0
        for i in range(0, self.num_rows):
            temp = reader.next()
            if int(temp[0])==session_id:
                return found
            else:
                found+=1
        return -1
    
    def append_session(self, session_id=-1):
        """Deletes that record from the file and returns the existing
        data in self.temp_buffer so that further recording can be done"""
        reader = csv.reader(open(self.activity._jobject.file_path, "rb"))
        data_new = []
        #####Copy all data except row to be deleted, to a temporary buffer
        for row in reader:
            if int(row[0])!=session_id:
                data_new.append(row)
            else:
                self.temp_buffer=row
        ##Write the temporary buffer to the file again   
        writer = csv.writer(open(self.activity._jobject.file_path, "wb"))
        for i in range(0, len(data_new)):
            writer.writerow(data_new[i])
        self.making_row= True
    
    def delete_record(self, session_id=-1):
        """Delete the record identified by its session_id"""
        reader = csv.reader(open(self.activity._jobject.file_path, "rb"))
        data_new = []
        #found  = -1
        ##Copy all data except row to be deleted, to a temporary buffer
        for row in reader:
            if int(row[0])!=session_id:
                data_new.append(row)
                #print row
            else:
                pass
        #if found==-1:
        #    return found
        #print data_new[5]
        ####Write the temporary buffer to the file again   
        self.num_rows=len(data_new)
        writer1 = csv.writer(open(self.activity._jobject.file_path, "w"))
        for i in range(0, len(data_new)):
            writer1.writerow(data_new[i])
    
    def get_existing_sessions_num(self):
        """Returns the number of existing sessions already done in that
        instance of the Activity"""
        return self.num_rows
    
    def get_records_values(self):
        pass
    
    def get_records_session_ids(self):
        pass
        
    def get_records_users(self):
        pass

    def get_all_records(self):
        """Gets the 2d array of all records"""
        records = []
        reader = csv.reader(open(self.activity._jobject.file_path, "rb"))
        for row in reader:
            temp_row = [int(x) for x in row]
            records.append(temp_row)
        return array(records)

    def take_screenshot(self, waveform_id=1):
        """ Take a screenshot and save to the Journal """
        act_root = environ['SUGAR_ACTIVITY_ROOT'] 
        tmp_dir = join(act_root, 'data')
        tmp_fd, file_path = mkstemp(dir=tmp_dir)
        ###TODO: This is such a crappy way to write a file to the journal
        ### Ideally to be implemented with write_file and read_file methods
        os.chmod(file_path, 0777)   
        gtk.threads_enter()
        window = gtk.gdk.get_default_root_window()
        width, height = window.get_size()
        x_orig, y_orig = window.get_origin()
        screenshot = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, has_alpha=False, \
                                    bits_per_sample=8, width=width, \
                                    height=height)
        screenshot.get_from_drawable(window, window.get_colormap(), x_orig, \
                                     y_orig, 0, 0, width, height)
        screenshot.save(file_path, "png")
        gtk.threads_leave()
        try:
            jobject = datastore.create()
            try:
                jobject.metadata['title'] = "%s %d" % (_('Waveform'),
                                                       waveform_id)
                jobject.metadata['keep'] = '0'
                jobject.metadata['buddies'] = ''
                jobject.metadata['preview'] = ''
                jobject.metadata['icon-color'] = \
                    self.activity.icon_colors
                jobject.metadata['mime_type'] = 'image/png'
                jobject.file_path = file_path
                datastore.write(jobject)
            finally:
                jobject.destroy()
                del jobject
        finally:
            os.close(tmp_fd)
            os.remove(file_path)


