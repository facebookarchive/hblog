#!/usr/bin/env python2.7

# Copyright 2013 Facebook, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import re
import sys
import socket
import base64
import getopt
import subprocess
import Queue
import time
import copy
import os
import glob
import json
from datetime import datetime, timedelta

from SingleFileLogAccessor import \
    SingleFileLogAccessor, SingleFileLogAccessorException

class LogAccessorException (Exception):
    '''Raised by the LogAccessor routines'''
    pass

class LogAccessor():

    # --------------------------------------------------------------------------
    # Public
    # --------------------------------------------------------------------------

    def __init__(self, log_path_glob, max_klines,
                       sampling_rate=None, verbose=False, debug=False):

        # Private instance variables
        self.debug = debug
        if self.debug:
            self.verbose = True
        else:
            self.verbose = verbose

        self.bytes_read = 0
        self.lines_read = 0

        self.open_logfiles = []
        self.open_logfiles_map = {}
        self.next_rec = None
        self.universal_offset = {'filename': None, 'byte_offset': None}

        self.logline_generator = None

        log_files = glob.glob(log_path_glob)
        if len(log_files) == 0:
            LogAccessorException(
                "ERROR: No log files matched %s" % log_path_glob)

        if len(log_files) > 1000:
            LogAccessorException(
                "ERROR: More than 1000 log files matched %s" % log_path_glob)

        for filename in log_files:
            if not filename.endswith('.gz') and os.stat(filename).st_size > 10:
                try:
                    logfile = SingleFileLogAccessor(filename,
                                             sampling_rate=sampling_rate,
                                             max_klines=max_klines,
                                             debug=self.debug,
                                             verbose=self.verbose)
                except SingleFileLogAccessorException as e:
                    self.err(("DEBUG: When reading %s "
                     "lib/LogAccessor.py caught: %s") % (filename, e))
                    self.err("INFO: Skipping bad file %s" % filename)
                else:
                    self.open_logfiles.append(logfile)

        # Sort !
        self.open_logfiles.sort(cmp=self.compare_logfile_start_ts)

        for logfile_id in range(len(self.open_logfiles)):
            logfile = self.open_logfiles[logfile_id]
            self.open_logfiles_map[logfile.get_filename()] = logfile_id

        if len(self.open_logfiles) == 0:
            raise LogAccessorException(
                "ERROR: Could not read first record from "
                "any of these files %s" % log_path_glob)

        self.universal_offset = {
            'filename': self.open_logfiles[0].get_filename(),
            'byte_offset': self.open_logfiles[0].get_byte_offset()
        }
        self.logline_generator = self.next_def()

    def close_all_files(self):
        for single_file_log_accessor in self.open_logfiles:
            if self.verbose:
                self.err("INFO: Closing " + single_file_log_accessor.filename)
            single_file_log_accessor.python_file_object.close()

    def __iter__(self):
        return self

    def next(self):
        return self.logline_generator.next()

    def next_def(self):
        logfile_id = self.logfile_name_to_id(self.universal_offset['filename'])
        remaining_open_logfiles = self.open_logfiles[logfile_id:]

        if self.debug:
             self.err("DEBUG: Universal offset %s" % self.universal_offset)
             self.err("       open_logfiles_map %s" % self.open_logfiles_map)
             self.err("       logfile_id %s" % logfile_id)
             for logfile in remaining_open_logfiles:
                 self.err("  remaining_logfiles %s" % logfile.get_filename())

        for logfile in remaining_open_logfiles:
            if self.verbose:
                    self.err("INFO: Processing new logfile" +
                             ("'%s'. " % logfile.get_filename()))

            try:
                for rec in logfile:
                    self.next_rec = logfile.look_one_rec_ahead()
                    self.universal_offset = {
                        'filename': logfile.get_filename(),
                        'byte_offset': logfile.get_byte_offset()
                    }
                    self.bytes_read += logfile.get_bytes_read()
                    self.lines_read += logfile.get_lines_read()

                    yield rec

            except StopIteration:
                if self.verbose:
                    self.err("INFO: End of file reached for " +
                             ("'%s'. " % logfile.get_filename()))

        if self.verbose:
            self.err("INFO: Reached end of the last logfile")
            raise StopIteration

    def get_bytes_read(self):
        return self.bytes_read

    def get_lines_read(self):
        return self.lines_read

    def seek_offset(self, universal_offset):
        logfile_id = self.logfile_name_to_id(universal_offset['filename'])
        remaining_open_logfiles = self.open_logfiles[logfile_id:]

        offset = universal_offset['byte_offset']
        for logfile in remaining_open_logfiles:
            try:
                logfile.seek_offset(offset)
            except StopIteration:
                if self.verbose:
                    self.err("INFO: End of file reached. " +
                             ("Filename was '%s'." % logfile.get_filename) +
                             "Will start reading next logfile.")
                offset = 0
            else:
                self.universal_offset = universal_offset
                self.logline_generator = self.next_def()  # restart generator
                self.logline_generator.next()  # go to first record
                return

        if self.verbose:
            self.err("INFO: Seeked to end of the last logfile")

    def seek_time(self, timestamp):
        for logfile_id in range(len(self.open_logfiles)):
            logfile_found = True
            next_logfile = None
            logfile = self.open_logfiles[logfile_id]

            try:
                next_logfile = self.open_logfiles[logfile_id + 1]
            except IndexError:
                logfile_found = True

            if next_logfile and next_logfile.first_rec['ts'] < timestamp:
                logfile_found = False

            if logfile_found:
                if self.debug:
                    self.err('DEBUG: found the desired logfile')

                logfile.seek_time(timestamp)

                self.universal_offset = \
                    {'filename': logfile.get_filename(),
                     'byte_offset': logfile.get_byte_offset()}

                self.logline_generator = self.next_def()  # restart generator
                self.logline_generator.next()  # go to first record

                return

    def look_one_rec_ahead(self):
        return self.next_rec

    def get_universal_offset(self):
        return self.universal_offset

    # --------------------------------------------------------------------------
    # Private
    # --------------------------------------------------------------------------

    def logfile_name_to_id(self, filename):
        if self.open_logfiles_map.has_key(filename):
            return self.open_logfiles_map[filename]
        else:
            raise LogAccessorException("LogAccessor was not able to open "
                "the logfile %s" % filename)

    def err(self, line):
        sys.stderr.write(line + "\n")

    def compare_logfile_start_ts(self, x, y):
        return cmp(x.first_rec['ts'], y.first_rec['ts'])
