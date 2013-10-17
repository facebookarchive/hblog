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

        def syslog_timestamp_transform(s):
            s = re.sub(' ([0-9]) ', r' 0\1 ', s)  # pad with 0s any single digit
            s = re.sub(' +', ' ', s)  # remove duplicate spaces
            s = "%s %s" % (datetime.now().year, s)  # imply this year
            return s

        def gclog_timestamp_transform(s):
            # chop off the timezone info, because
            # %z, documented as "UTC offset in the form +HHMM or -HHMM",
            # is not fully supported python 2.3 thru 2.7 in datetime.strptime
            s = re.sub(re.compile(r'-?\d{4}$'), '', s)
            return s

        # RE's will be checked in the order as the appear in LOGLINE_RE_LIST
        # NOTE: all re's must have four groups:
        #       (1) timestamp; (2) log level; (3) something to ignore; (4) body;
        self.LOGLINE_RE_LIST = [
            {'re': re.compile(
             r'(\d\d\d\d\-\d\d\-\d\d \d\d:\d\d:\d\d,\d+) +(\[.*?\])? *(\w+) +(.+)\n'
             ),
             'time_format': '%Y-%m-%d %H:%M:%S,%f',
             'timestr_transform': None,
             'comments': 'log4j format. E.g. "2013-12-30 23:50:50,121"'},

            {'re': re.compile(
             r'([A-Za-z]{3} +\d{1,2} +\d\d:\d\d:\d\d) *()?()?(.+)\n'
             ),
             'time_format': '%Y %b %d %H:%M:%S',
             'timestr_transform': syslog_timestamp_transform,
             'comments': 'typical syslog format. E.g. "Oct  1 13:57:31"'},

            {'re': re.compile(
              r'(\d\d\d\d\-\d\d\-\d\dT\d\d:\d\d:\d\d.\d+-?\d*): *()?()?(.+)\n'
             ),
             'time_format': '%Y-%m-%dT%H:%M:%S.%f',
             'timestr_transform': gclog_timestamp_transform,
             'comments': 'java garbage collection log format. '
                'E.g. "2013-09-30T23:12:58.800-0700: 716.601: [GC: [ParNew"'},
        ]

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
        except IOError as e:
            self.err(("WARNING: When reading %s "
                     "lib/SingleFileLogAccessor.py caught: %s") % (filename, e))
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
                    if self.debug:
                        self.err('DEBUG: next_line """%s"""' % next_line)

                    m = False
                    for logline_re in self.LOGLINE_RE_LIST:
                        m = logline_re['re'].match(next_line)
                        if m:
                            if self.debug:
                                self.err('DEBUG: MATCHED %s' %
                                                       logline_re['re'].pattern)

                            ts = self.str_to_time(m.group(1),
                                          time_format=logline_re['time_format'],
                                      transform=logline_re['timestr_transform'])
                            break

                    if m:
                        r = {'ts': str(ts),
                             'level': m.group(3),
                             'text': m.group(4)}

                        if r['level'] not in self.ALL_LEVELS:
                            if self.debug:
                                self.err('DEBUG: Could not parse Level '
                                    '(got "%s") from "%s. Defaulting to WARN"' %
                                                        (r['level'], next_line))
                            r['level'] = 'WARN'

                        (r['norm_text'], r['fp']) = self.squeeze(r['text'])
                        self.next_rec = r

                        if self.debug:
                            self.err('DEBUG: binsearch trace - %s' %
                                                      self.next_rec['ts'])

                            self.err('DEBUG:                     ' +
                                                      self.get_filename())
                            self.err('DEBUG:                     ' +
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
                                     'text': next_line.rstrip(),
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

        f = hashlib.md5(s).hexdigest()

        return (s, f)

    def str_to_time(self, s, time_format, transform):
        if transform:
            s = transform(s)
        return datetime.strptime(s, time_format)  # datetime object

    def err(self, line):
        sys.stderr.write(str(line) + "\n")

    def get_python_file_object_byte_offset(self):
        return self.python_file_object.tell()
