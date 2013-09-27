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
import hashlib
import base64
import getopt
import subprocess
import Queue
import time
import copy
import os
import json
import random
from datetime import datetime, timedelta

class SingleFileLogAccessorException(Exception):
    '''Raised by the SingleFileLogAccessor routines'''
    pass

class SingleFileLogAccessor():
    """ The file is expected to be in the typical log format with
        timestamps at the beginning. No attempt is made to understand
        daylight savings.  Log lines are also "fingerprinted", usually
        able to assign matching fingerprints to log lines that differ
        only by timestamp, specific host names, or other variable arguments
        to a given log format string at the time it was written to the log"""

    # --------------------------------------------------------------------------
    # Public
    # --------------------------------------------------------------------------
    def __init__(self, filename,
        max_klines=2000, sampling_rate=None, verbose=False, debug=False):

        self.debug = debug
        if self.debug:
            self.verbose = True
        else:
            self.verbose = verbose

        self.sampling_rate = sampling_rate
        self.seeking = False

        time_re = "\d\d\d\d\-\d\d\-\d\d \d\d:\d\d:\d\d,\d+"
        self.LOGLINE_RE = re.compile(
          "(%s) +(\[.*?\])? *(\w+) +(.+)\n" % time_re)

        self.STRPTIME_FORMAT = '%Y-%m-%d %H:%M:%S,%f'

        self.SQUEEZE_RE = (
            (re.compile(r"\{.+\}"), "{ ... }"),    # sketchy, but seems right
            (re.compile(r"\{.+\}"), "{ ... }"),    # sketchy, but seems right
            (re.compile(r"\(.+\)"), "( ... )"),    # sketchy, but seems right

            # Hosts
            (re.compile(r"[.a-z0-9]{3,}\.com"), "<<HOST>>"),

            # IPv4s
            (re.compile(r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}"), "<<IP>>"),

            # short hex numbers must have leading @ or x
            (re.compile(r"([\@xX])[\dabcdefABCDEF]+"), r"\1#"),

            # longer hex numbers are less ambiguous
            (re.compile(r"[\dabcdefABCDEF]{6,}"), r"#"),

            # longer hex numbers are less ambiguous
            (re.compile(r"-?[\d#]+"), "#"),           # any digits

            # mostly region filenames
            (re.compile(r"hdfs://[A-z\d#-:/]*"), "hdfs://##"),
            (re.compile(r"/[A-z\d#-:/]*"), "/##"),  # other pathnames
            #(re.compile(TABLENAMES), "#tablename#")
        )

        # Defaults
        self.ALL_LEVELS = ["INFO", "DEBUG", "WARN", "ERROR", "FATAL"]
        self.MAX_LINE_LENGTH = 100 * 1000
        self.MAXGB = 5
        self.MAX_KLINES = max_klines

         # bail if timestamps cant be found at the beginning of the file
        self.FIRST_REC_MAX_LINES = 100
        self.FIRST_REC_MAX_BYTES = 10 * 1000

        self.num_unrecognized_lines = 0
        self.bytes_read = 0
        self.lines_read = 0

        self.python_file_object = None
        self.current_offset = None
        self.filename = None
        self.file_size = None
        self.first_rec = None
        self.previous_rec = None
        self.next_rec = None

        self.filename = filename
        self.logline_generator = self.next_def()

        if self.debug:
            self.err("DEBUG: Opening %s" % filename)

        try:
            self.python_file_object = open(filename, "r")
        except IOError, e:
            self.err("WARNING: Could not open file %s," % filename)
            self.err(e)
        else:
            self.file_size = os.fstat(self.python_file_object.fileno()).st_size

            # Find the first line
            try:
                self.seeking = True  # this will turn off sampling and \
                                     # unrecognized lines
                if self.debug:
                    self.err('DEBUG: Getting first line of %s' % filename)
                self.next()
                self.seeking = False

                self.first_rec = self.next_rec
            except StopIteration:
                raise SingleFileLogAccessorException("Could not read the "
                    "first line of %s" % filename)

    def __iter__(self):
        return self

    def next(self):
        return self.logline_generator.next()

    def next_def(self):
        next_line = 'BOF'

        while next_line:
            self.current_offset = self.get_python_file_object_byte_offset()
            next_line = self.python_file_object.readline(self.MAX_LINE_LENGTH)

            if self.seeking or not self.sampling_rate or \
                                          random.random() <= self.sampling_rate:
                self.lines_read += 1
                self.bytes_read += len(next_line)

                current_rec = self.next_rec

                # If this is the 1st record ...
                if not current_rec:
                    # First good line must be close the beginning of file
                    if self.bytes_read > self.FIRST_REC_MAX_BYTES:
                        raise SingleFileLogAccessorException(
                                    "ERROR: Refusing to read more than "
                                    "%d bytes to find the first record" %
                                    self.FIRST_REC_MAX_BYTES)

                    # First good line must be close the beginning of file
                    if self.lines_read > self.FIRST_REC_MAX_LINES:
                        raise SingleFileLogAccessorException(
                                    "ERROR: Refusing to read more than "
                                    "%d lines to find the first record" %
                                    self.FIRST_REC_MAX_LINES)

                if self.lines_read > self.MAX_KLINES * 1000:
                    raise SingleFileLogAccessorException(
                                "ERROR: Refusing to read more than"
                                " %d k lines per logfile" %
                                self.MAX_KLINES)

                if self.lines_read > self.MAXGB * 1024 * 1024 * 1024:
                    raise SingleFileLogAccessorException(
                            "ERROR: Refusing to read more than"
                            " %d GB per logfile" % self.MAXGB)

                # Skip empty lines
                if len(next_line) > 0:
                    m = self.LOGLINE_RE.match(next_line)
                    if m:
                        r = {'ts': str(self.str_to_time(m.group(1))),
                             'level': m.group(3),
                             'text': m.group(4)}

                        if r['level'] not in self.ALL_LEVELS:
                            self.err('WARNING: Could not parse Level '
                                '(got "%s") from "%s"' % (r['level'], next_line))
                        else:
                            (r['norm_text'], r['fp']) = self.squeeze(r['text'])
                            self.next_rec = r

                            if self.debug:
                                self.err('DEBUG: binsearch trace - %s' %
                                                          self.next_rec['ts'])

                                self.err('DEBUG:                     ' + \
                                                          self.get_filename())
                                self.err('DEBUG:                     ' + \
                                                                    next_line)

                            yield current_rec
                    else:
                        self.num_unrecognized_lines += 1

                        if current_rec and not self.seeking:
                            if self.sampling_rate and self.sampling_rate < 1:
                                if self.debug:
                                    self.err('DEBUG: not fetching any '
                                        'unrecognized lines when sampling')
                            else:
                                # timestamp and level for unrecognized lines
                                # will be attributed from the previous line
                                r = {'ts': current_rec['ts'],
                                     'level': current_rec['level'],
                                     'text': next_line,
                                     'unrecognized_line': True}

                                (r['norm_text'], r['fp']) = self.squeeze(r['text'])
                                self.next_rec = r

                                if self.debug:
                                    self.err('DEBUG: fetching unrecognize line')
                                    self.err('DEBUG: attributing to %s' %
                                                              self.next_rec['ts'])
                                    self.err('DEBUG:                     ' + \
                                                          self.get_filename())
                                    self.err('DEBUG:                 ' + next_line)

                                yield current_rec

        if self.next_rec:
            last = self.next_rec
            self.next_rec = None
            yield last

    def get_filename(self):
        return self.filename

    def get_byte_offset(self):
        return self.current_offset

    def get_bytes_read(self):
        return self.bytes_read

    def get_lines_read(self):
        return self.lines_read

    def look_one_rec_ahead(self):
        return self.next_rec

    def seek_offset(self, offset):
        self.python_file_object.seek(offset)
        self.seeking = True  # this will turn off sampling and \
                             # unrecognized lines
        self.next()
        self.seeking = False

    def seek_time(self, timestamp):
        """try to get within 32k bytes before the timesamp"""

        self.seeking = True  # this will turn off sampling and \
                             # unrecognized lines

        close_enough = 32768
        start = 0
        end = self.file_size
        self.seek_offset(start)

        # Binary search
        if self.next_rec['ts'] < timestamp:
            while end - start > close_enough and self.next_rec:
                midpoint = int((end + start) / 2)
                self.seek_offset(midpoint)
                if self.next_rec['ts'] < timestamp:
                    start = midpoint
                else:
                    end = midpoint

        # last seek was midpoint, which can be too far
        self.seek_offset(start)

        if self.debug:
            self.err("DEBUG: binsearch trace - CLOSE ENOUGH, SCANNING")

        if not self.next_rec:
            raise SingleFileLogAccessorException(
                    "Binary search could not find any "
                    "loglines that match LOGLINE_RE")

        # Scan once close_enough
        while self.next_rec and \
                                      self.next_rec['ts'] < timestamp:
            if self.debug:
                self.err("DEBUG: binsearch trace - ... scan ...")
            self.next()

        self.seeking = True

    # --------------------------------------------------------------------------
    # Private
    # --------------------------------------------------------------------------
    def squeeze(self, s):
        """ remove stuff that would  make simlar lines appear different:
        squeeze out all digits, plus anything between parens
        there will probably be a lot of weird loglines that
        defeat this, like hex numbers, but it's fine for most """

        for m, r in self.SQUEEZE_RE:
            s = re.sub(m, r, s)

        f = base64.b64encode(hashlib.md5(s).digest())[:8]

        return (s, f)

    def str_to_time(self, s):
        return datetime.strptime(s, self.STRPTIME_FORMAT)  # datetime object

    def err(self, line):
        sys.stderr.write(line + "\n")

    def get_python_file_object_byte_offset(self):
        return self.python_file_object.tell()
