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

from optparse import OptionParser

import os
SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))

import re

import sys
import urlparse
import pprint
from datetime import datetime, timedelta
import json

sys.path.insert(0, SCRIPT_PATH + '/../tornado')
import tornado.ioloop
import tornado.web

sys.path.insert(0, SCRIPT_PATH + '/../lib')
from LogAccessor import LogAccessor, LogAccessorException

ALL_LEVELS = ["INFO", "DEBUG", "WARN", "ERROR", "FATAL"]

def err(line):
    if not isinstance(line, basestring):
        line = pprint.pformat(line)
    sys.stderr.write(line + "\n")

def summarize(results):
    fingerprint_summary = {}
    level_summary = {}
    regex_summary = {}
    level_summary = dict(zip(ALL_LEVELS, (0, 0, 0, 0, 0)))

    for logline in results:
        level_summary[logline[r'level']] += 1

        if logline[r'fp'] not in fingerprint_summary:
            fingerprint_summary[logline[r'fp']] = \
                {'fp': logline[r'fp'], 'count': 0,
                 'level': logline[r'level'],
                 'norm_text': logline[r'norm_text']}
        fingerprint_summary[logline[r'fp']]['count'] += 1

    summary = {'level': level_summary,
               'fp': fingerprint_summary,
               'regex': regex_summary}

    return summary

class HBLogHandlersParent(tornado.web.RequestHandler):
    def parse_url_args(self):
        url_args = urlparse.parse_qs(self.request.query)
        for key, val in url_args.items():
            url_args[key] = url_args[key][0].split(',')

        if url_args.has_key("sampling-rate") and \
                                         url_args["sampling-rate"][0] != "None":
            self.sampling_rate = float(url_args["sampling-rate"][0])
        else:
            self.sampling_rate = None

        self.logs_glob = url_args['glob'][0]

        for i in ['fp', 'fp-exclude', 're', 're-exclude']:
            if not url_args.has_key(i):
                url_args[i] = []

        err("%s INFO %s %s %s" %
            (
                datetime.now(),
                self.request.uri,
                self.sampling_rate,
                self.logs_glob,
            ))

        self.url_args = url_args

    def fetch_and_filter(self, log_accessor):
        if self.url_args.has_key("universal-offset"):
            filename, byte_offset = \
                                 self.url_args["universal-offset"][0].split(':')
            universal_offset = {'byte_offset': int(byte_offset),
                                'filename': filename}

            if self.settings['verbose']:
                err("seeking to %s ..." % universal_offset)

            log_accessor.seek_offset(universal_offset)

        else:
            start_time = self.url_args["start"][0]
            end_time = self.url_args["end"][0]

            seek_time_str = str(start_time).split('.')[0]

            if self.settings['verbose']:
                err("seeking to %s ..." % seek_time_str)

            log_accessor.seek_time(seek_time_str)

        if self.settings['verbose']:
            err("--------------- seeked to --------------")
            err(log_accessor.look_one_rec_ahead())
            err("----------------------------------------")

        previous_line = None  # timestamp and level for unrecognized lines
                              # will be attributed from the previous line
                              # in the SingleFileLogAccessor library class
        for line in log_accessor:
            if 'unrecognized_line' in line.keys() and line['unrecognized_line']:
                if not previous_line:
                    if self.settings['verbose']:
                        err("Got unrecognized line "
                                            "before any recognized line in %s" %
                                            log_accessor.get_universal_offset())

            elif not self.url_args.has_key("universal-offset") and \
                                                          line['ts'] > end_time:
                if self.settings['verbose']:
                    err("----- reached end-time at --------------")
                    err(line)
                    err("----------------------------------------")

                raise StopIteration
                # for unrecognized lines don't StopIteration

            if line['level'] in self.url_args['levels-list']:
                if self.url_args['fp'] == []:
                    if not any([True for fpex in self.url_args['fp-exclude'] if
                                                  line['fp'].startswith(fpex)]):
                        take_it = False
                        if self.url_args['re'] == []:
                            take_it = True
                        for r in self.url_args['re']:
                            if re.search(r, line['text'], re.IGNORECASE):
                                take_it = True
                        for r in self.url_args['re-exclude']:
                            if re.search(r, line['text'], re.IGNORECASE):
                                take_it = False
                        if take_it:
                            yield line
                elif any([True for fp in self.url_args['fp'] if
                                                    line['fp'].startswith(fp)]):
                    yield line

            previous_line = line

class MainHandler(HBLogHandlersParent):
    def get(self):
        self.set_header("Content-Type", "text/html")
        href_example_list = ["/log/stream",
                             "/log/summary"]
        self.write("<pre>\n")
        self.write("Examples:\n")
        for href in href_example_list:
            self.write("<a href=\"%s\">%s</a>\n" % (href, href))
        self.write("</pre>\n")

class LogStream(HBLogHandlersParent):
    def get(self):
        self.set_header("Content-Type", "text/plain")
        self.parse_url_args()

        if self.settings['verbose']:
            err("basedir %s" % self.settings["basedir"])


        if self.url_args.has_key("universal-offset"):
            max_klines = 3  # tail -f is different and  needs to fail faster
        else:
            max_klines = 20000

        log_accessor = LogAccessor(self.logs_glob, max_klines=max_klines,
                                   sampling_rate=self.sampling_rate,
                                   verbose=self.settings['verbose'],
                                   debug=self.settings['debug'],
                                  )

        for line in self.fetch_and_filter(log_accessor):
            line_pkg = {'pkg-cls': 'log-accessor-line', 'pkg-obj': line}
            self.write("%s\n" % json.dumps(line_pkg))

        log_accessor.close_all_files()

        line_pkg = {'pkg-cls': 'exit-status',
                    'pkg-obj':
                      {'status': 'success',
                       'universal-offset': log_accessor.get_universal_offset()}
                    }
        self.write("%s\n" % json.dumps(line_pkg))

class LogSummary(HBLogHandlersParent):
    def get(self):
        self.set_header("Content-Type", "text/plain")
        self.parse_url_args()

        log_accessor = LogAccessor(self.logs_glob, max_klines=20000,
                                   sampling_rate=self.sampling_rate,
                                   verbose=self.settings['verbose'],
                                   debug=self.settings['debug'],
                                  )

        results = []
        for line in self.fetch_and_filter(log_accessor):
            results.append(line)

        log_accessor.close_all_files()

        summary = summarize(results)
        line_pkg = {'pkg-cls': 'log-accessor-line', 'pkg-obj': summary}
        self.write("%s\n" % json.dumps(line_pkg))

        line_pkg = {'pkg-cls': 'exit-status',
                    'pkg-obj': {'status': 'success'}
                   }

        self.write("%s\n" % json.dumps(line_pkg))


if __name__ == "__main__":
    usage = "%prog: [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("--basedir", default="/tmp/hblog/test_logs",
        help="Base dir for all log dirs (def: %default)")
    parser.add_option("--verbose", "-v", action="store_true", default=False,
        help="Verbose logging")
    parser.add_option("--debug", "-d", action="store_true", default=False,
        help="Very verbose logging")

    options, _ = parser.parse_args()
    options = vars(options)  # convert object to dict

    if options['debug']:
        options['verbose'] = True

    application = tornado.web.Application([
                   (r"/", MainHandler),
                   (r"/log/stream", LogStream),
                   (r"/log/summary", LogSummary)
               ],
               **options)

    application.listen(6957, '0.0.0.0')
    tornado.ioloop.IOLoop.instance().start()
