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

from optparse import OptionParser, OptionGroup

import re
import sys
import getopt
import subprocess
import time
import copy
import os
import json
import pprint
import urllib
from datetime import datetime, timedelta
from collections import defaultdict

SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))

sys.path.insert(0, SCRIPT_PATH + '/../tornado')
import tornado.httpclient
import tornado.ioloop

def err(line):
    if not isinstance(line, basestring):
        line = pprint.pformat(line)
    sys.stderr.write(line + "\n")

class HBLogEventsException(Exception):
    pass

class HBLogEvents:
    def __init__(self, options):
        self.http_options = {}
        self.options = options
        self.initial_hosts_list = list(self.options['hosts-list'])

        self.http_clients_started = []
        self.http_clients_finished = []
        self.results_per_host = {}
        self.summaries_per_host = {}
        self.exit_state_per_host = {}

        self.io_loop = tornado.ioloop.IOLoop.instance()

        self.io_loop.add_callback(self.start_the_world_event)
        self.io_loop.start()

    def exit_on_exception(func):
        def decorator(self, *args):
            try:
                func(self, *args)
            except Exception:
                self.io_loop.stop()
                raise
        return decorator

    def exit_on_return(func):
        def decorator(self):
            func(self)
            self.io_loop.stop()

        return decorator

    @exit_on_exception
    def start_the_world_event(self):
        self.http_options['sampling-rate'] = self.options['sample']
        if len(self.options['fp']) > 0:
            self.http_options['fingerprints'] = ",".join(self.options['fp'])

        dont_pass_to_http = ['hosts-list', 'log-tiers-hosts', 'log-tiers-globs']
        for key, val in self.options.items():
            if not key in dont_pass_to_http:
                if hasattr(val, "__iter__") and not isinstance(val, basestring):
                    self.http_options[key] = ",".join(val)
                else:
                    self.http_options[key] = val

        if self.options['mode'] == 'summary':
            self.http_options['data_type'] = "summary"
            self.http_options['tail'] = "1:00"  # last 1 min

        elif self.options['mode'] == 'details':
            self.http_options['data_type'] = "stream"
            self.http_options['tail'] = "1:00"  # last 1 min

        elif self.options['mode'] == 'follow':
            self.http_options['data_type'] = "stream"

        self.io_loop.add_callback(self.start_http_clients_event)

    @exit_on_exception
    def start_http_clients_event(self):
        self.http_clients_started = []
        self.http_clients_finished = []
        self.results_per_host = {}

        for tier in self.options['log-tiers']:
            for host in self.options['log-tiers-hosts'][tier]:
                if host in self.options['hosts-list']:

                    self.http_clients_started.append(host)

                    host_specific_http_options = {}
                    for key, val in self.http_options.items():
                        if val:
                            host_specific_http_options[key] = val

                    if 'offsets_per_host' in self.http_options:
                        host_specific_http_options['offsets_per_host'] = None
                        if host in self.http_options['offsets_per_host']:
                            host_specific_http_options["universal-offset"] = \
                                self.http_options['offsets_per_host'][host]

                    host_specific_http_options['glob'] = \
                        self.options['log-tiers-globs'][tier]

                    url = "http://%s:6957/log/%s?%s" % \
                                  (host,
                                   self.http_options['data_type'],
                                   urllib.urlencode(host_specific_http_options))

                    if self.options['verbose']:
                        err("URL: %s" % url)

                    http_client = tornado.httpclient.AsyncHTTPClient()
                    http_client.fetch(url, self.finish_http_client_event,
                                         connect_timeout=2.0,
                                         request_timeout=20.0)

        if self.options['verbose']:
            err("Start %d / %d" % \
                (len(self.http_clients_started),
                 len(self.options['hosts-list'])))

    def finish_http_client_event(self, response):
        host = response.request.url.replace('http://', '').split(':')[0]

        if self.options['verbose']:
            err("Processing: %s" % host)

        if response.error:
            err("WARN: HTTP error from %s, blacklisting host. Error was %s." % \
                                                         (host, response.error))

            if host in self.options['hosts-list']:
                self.options['hosts-list'].remove(host)

            if host in self.http_clients_started:
                self.http_clients_started.remove(host)  # As if it never started
                                                        # to halp check for the
                                                        # last http_client reach
        else:
            if host not in self.results_per_host.keys():
                self.results_per_host[host] = []

            for line in response.body.split("\n"):
                if len(line) > 0:
                    line_pkg = self.import_from_json(line)
                    if line_pkg['pkg-cls'] == 'log-accessor-line':
                        self.results_per_host[host].append(line_pkg['pkg-obj'])
                    elif line_pkg['pkg-cls'] == 'exit-status':
                        self.exit_state_per_host[host] = line_pkg['pkg-obj']
                        if self.options['verbose']:
                            err("STATUS: %s %s" % (host, line_pkg['pkg-obj']))

            self.http_clients_finished.append(response)

        if len(self.options['hosts-list']) == 0:
            msg = "All %d hosts got blacklisted" % len(self.initial_hosts_list)
            print(" ".join([str(tail_time_from_str('0:00')),
                              'BLACKL02', 'ERROR',  '-', msg
                          ])
                 )
            err("ERROR: %s" % msg)
            tornado.ioloop.IOLoop.instance().stop()

        #
        # Did we reach the last http_client ?
        #
        if len(self.http_clients_finished) >= len(self.http_clients_started):
            if self.options['mode'] == 'details' or \
                                               self.options['mode'] == 'follow':
                self.io_loop.add_callback(self.print_details_event)

            else:
                assert self.http_options['data_type'] == "summary", \
                       "Wrong HTTP datatype %s, expected 'summary'" % \
                       (self.http_options['data_type'])

                for host, summary in self.results_per_host.items():
                    if self.options['verbose']:
                        err("Host:")
                        err(host)

                        err("Results:")
                        err(pprint.pformat(summary))

                    if len(summary) == 0:
                        err("ERROR: Got an empty list for the host summary")
                        tornado.ioloop.IOLoop.instance().stop()

                    #  Merge summaries of a single host
                    summary_merged = {'fp': {}, 'level': defaultdict(int)}
                    for s in summary:
                        for fp_key in s['fp'].keys():
                            if fp_key in summary_merged['fp'].keys():
                                summary_merged['fp'][fp_key]['count'] += \
                                                        s['fp'][fp_key]['count']
                            else:
                                summary_merged['fp'][fp_key] = s['fp'][fp_key]

                        for level_key in s['level'].keys():
                            summary_merged['level'][level_key] += \
                                                           s['level'][level_key]

                    # Summaries are one-line per result
                    self.summaries_per_host[host] = summary_merged

                self.io_loop.add_callback(self.print_summary_event)

    @exit_on_return
    @exit_on_exception
    def print_summary_event(self):
        EXCEPTIONS = {}

        print_fingerprints = []
        fp_summary = {}

        for host, summary in self.summaries_per_host.items():
            for fp in summary['fp'].keys():
                value = summary['fp'][fp]
                if fp not in fp_summary:
                    fp_summary[fp] = copy.deepcopy(value)
                else:
                    fp_summary[fp]['count'] += value['count']

        print("---------------------------------------------------------------")
        print("Fingerprint summary:")
        if len(fp_summary.keys()) > 0:
            print "%7s  %-12s  %-6s       %s" % \
                                       ('count', 'fingerprint', 'level', 'text')
            print
        else:
            print "No matching lines found"

        summary_width = TERMINAL_WIDTH - 34
        for l in sorted(fp_summary.values(), reverse=True):
            l['norm_text'] = l['norm_text'].replace('\t', '\\t')  # show tabs

            # Truncate fingerprints
            print_fingerprints.append(l['fp'])
            l['fp'] = l['fp'][0:7]

            print ("%(count)7d  %(fp)-12s  %(level)-6s %(norm_text)-" +
                str(summary_width) + "." + str(summary_width) + "s") % l

            i = summary_width
            while l['norm_text'][i:]:
                print "%29s" % "",
                print l['norm_text'][i: i + summary_width]
                i += summary_width

        print("---------------------------------------------------------------")
        print "Host sumary: "
        if self.options['fp']:
            print_fingerprints = self.options['fp']
        else:
            how_many_fps_will_fit = (TERMINAL_WIDTH - 19) / 11
            print_fingerprints = print_fingerprints[:how_many_fps_will_fit]

        if len(print_fingerprints) > 0:
            print
            print "%19.19s" % "",
            for fp in print_fingerprints:
                # Truncate fingerprints
                print "%-10s" % fp[0:7],
            print
            print

            for host, summaries in sorted(self.summaries_per_host.items()):
                fp_summary = summaries['fp']

                if len(fp_summary.keys()) > 0:
                    print "%16.16s" % host,
                    for fp in print_fingerprints:
                        fp_matches = [i for i in fp_summary.keys() if
                                                             i.startswith(fp)]
                        if len(fp_matches) == 1:
                            print "%10d" % fp_summary[fp_matches[0]]['count'],
                        elif len(fp_matches) > 1:
                            sys.stdout.write("WARNING: %s matched more then "
                                                     "one fingerprint\n" % fp)
                        else:
                            print "%10.10s" % "",
                    print

        print("---------------------------------------------------------------")
        print
        for host, exc in sorted(EXCEPTIONS.items()):
            print "%-30.30s    %s" % (host, exc)

        self.report_blacklisted_hosts()

    @exit_on_exception
    def print_details_event(self):
        all = []
        for host, results in self.results_per_host.items():
            for l in results:
                l['host'] = host
                all.append(l)

        for l in sorted(all, key=lambda x: x['ts']):
            l['text'] = l['text'].replace('\t', '\\t')  # show tabs

            # Truncate fingerprints
            l['fp'] = l['fp'][0:7]

            line = " ".join([l['ts'], l['fp'], l['level'].ljust(5), l['host'],
                            l['text']])
            if self.options['nowrap']:
                print line[0:TERMINAL_WIDTH]
            else:
                print line

        self.report_blacklisted_hosts()
        sys.stdout.flush()

        if self.options['mode'] == 'follow':
            # Update offsets
            self.http_options['offsets_per_host'] = {}
            for host, exit_state in self.exit_state_per_host.items():
                uo = exit_state['universal-offset']
                self.http_options['offsets_per_host'][host] = \
                    "%s:%s" % (uo['filename'], uo['byte_offset'])

            time.sleep(0.5)
            self.io_loop.add_callback(self.start_http_clients_event)
        else:
            tornado.ioloop.IOLoop.instance().stop()

    def report_blacklisted_hosts(self):
        blacklisted_hosts = \
            set(self.initial_hosts_list) - set(self.options['hosts-list'])
        if len(blacklisted_hosts) > 0:
            line =" ".join([str(tail_time_from_str('0:00')),
                              'BLACKL01', 'WARN ',  '-',
                              'Blacklisted %d hosts (of %d in this session): '
                              '%s - consider adding filters or '
                              'lowering the sampling rate' %
                              (len(blacklisted_hosts),
                               len(self.initial_hosts_list),
                               blacklisted_hosts
                              )
                          ])

            if self.options['nowrap']:
                print line[0:TERMINAL_WIDTH]
            else:
                print line

    def convert_keys_to_no_unicode(self, input_struct):
        if isinstance(input_struct, dict):
            return dict([(key.encode('utf-8'), value) for key, value in \
                                                      input_struct.iteritems()])
        elif isinstance(input_struct, list):
            return [self.convert_keys_to_no_unicode(element) for element in \
                                                                   input_struct]

        else:
            return input_struct

    def import_from_json(self, json_str):
        return self.convert_keys_to_no_unicode(json.loads(json_str))


try:
    tcols = os.popen('tput cols', 'r').read()
    TERMINAL_WIDTH = int(tcols)
except:
    TERMINAL_WIDTH = 100

def flatten(x):
   result = []
   for el in x:
       if hasattr(el, "__iter__") and not isinstance(el, basestring):
           result.extend(flatten(el))
       else:
           result.append(el)
   return result

def round_to_seconds(t):
    try:
        return t.strftime("%Y-%m-%d %H:%M:%S")
    except AttributeError:
        return timedelta(seconds=int(t.total_seconds()))

def tail_time_from_str(a):
    t = a.split(":")

    # parse shorthand time
    if t[0] == '' and len(t) == 2:
        t = [0, 0, t[1]]
    elif len(t) == 1:
        t = [0, t[0], 0]
    elif len(t) == 2:
        t = [0, t[0], t[1]]
    elif len(t) == 3:
        pass
    else:
        raise HBLogEventsException("invalid time format")

    t = [int(x) for x in t]

    return datetime.now() - \
        timedelta(hours=t[0], minutes=t[1], seconds=t[2])

def str_to_time(s):
    STRPTIME_FORMAT = '%Y-%m-%d %H:%M:%S,%f'
    return datetime.strptime(s, STRPTIME_FORMAT)

def run_sh(cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if stdout:
        stdout = stdout.rstrip()
    if stderr:
        stderr = stderr.rstrip()

    return (stdout, stderr, p.returncode)

def list_hosts_of_tier(tier_name):
    cmd = "list_hosts_of_tier.sh %s" % (tier_name)  # in PATH
    stdout, stderr, returncode = run_sh(cmd)

    if returncode == 0:
        return list(set(stdout.split("\n")))  # dedup
    elif returncode == 2:
        raise HBLogEventsException("Tier '%s' is not recognized by "
                                               "list_hosts_of_tier" % tier_name)

    else:
        raise HBLogEventsException(
            "Shelling-out returned non-zero exit status %d; "
            "Stdout: %s; Stderr: %s;" % (returncode, stdout, stderr))

# Map tier endings to globs
tier2glob_map_examples_for_localhost = {
    'nn': './var/log/example-hadoop-hadoop-avatarnode.log*',
    'nn-gc': './var/log/example-hadoop-hadoop-avatarnode-gc.log*',
    'syslog': './var/log/example-syslog-messages.log*',
}

tier2glob_map = {
    'endswith': {
        'dfs-nn': '/var/log/hadoop/*-DFS/hadoop-hadoop-avatarnode-[!g][!c]*',
        'dfs-nn-gc': '/var/log/hadoop/*-DFS/hadoop-hadoop-avatarnode-gc*',

        'dfs-slaves':
            '/var/log/hadoop/*-DFS/hadoop-hadoop-avatardatanode-[!g][!c]*',
        'dfs-slaves-gc':
            '/var/log/hadoop/*-DFS/hadoop-hadoop-avatardatanode-gc*',

        'hbase-master': '/var/log/hadoop/*-HBASE/hbase-hadoop-master-[!g][!c]*',
        'hbase-master-gc': '/var/log/hadoop/*-HBASE/gc-hbase*',

        'hbase-regionservers':
            '/var/log/hadoop/*-HBASE/hbase-hadoop-regionserver-[!g][!c]*',
        'hbase-thrift': '/var/log/hadoop/*-HBASE/hbase-hadoop-thrift-[!g][!c]*',

        'hbase-zookeepers':
            '/var/log/hadoop/*-HBASE/hbase-hadoop-zookeeper-[!g][!c]*',

        'zookeepers': '/var/log/hadoop/*-ZK/hbase-hadoop-zookeeper-[!g][!c]*',

        'mr-jt': '/var/log/hadoop/*-MR/hadoop-hadoop-jobtracker-[!g][!c]*',
        'mr-jt-gc': '/var/log/hadoop/*-MR/hadoop-hadoop-jobtracker-gc*',

        'mr-slaves': '/var/log/hadoop/*-MR/hadoop-hadoop-tasktracker-[!g][!c]*',
        'mr-slaves-gc': '/var/log/hadoop/*-MR/hadoop-hadoop-tasktracker-gc*',

        'syslog': '/var/log/system/messages*',
    },
    'startswith': {
    },
    're': {
    }
}

tier2glob_equivalents = {
    'endswith': {
        'dfs-sn': 'dfs-nn',
        'dfs-sn-gc': 'dfs-nn-gc',
        'hbase-secondary': 'hbase-master',
        'hbase-secondary-gc': 'hbase-master-gc',
        'hbase-regionservers-gc': 'hbase-master-gc',
    },
    'startswith': {
    },
    're': {
    }
}

def get_matched(logtier):
    tier_prefixes = (tier2glob_map['startswith'].keys() +
                                     tier2glob_equivalents['startswith'].keys())
    tier_prefixes.sort(key=len, reverse=True)  # tiebreaker, match longest
    prefixes_matches = [i for i in tier_prefixes if logtier.startswith(i)]

    tier_endings = (tier2glob_map['endswith'].keys() +
                                       tier2glob_equivalents['endswith'].keys())
    tier_endings.sort(key=len, reverse=True)  # tiebreaker, match longest
    endings_matches = [i for i in tier_endings if logtier.endswith(i)]

    tier_re_list = (tier2glob_map['re'].keys() +
                                       tier2glob_equivalents['re'].keys())
    re_matches = [i for i in tier_re_list if re.match(i, logtier)]

    if len(re_matches):
        matched = re_matches[0]  # match the first occurance
        match_type = 're'

    elif len(endings_matches):
        matched = endings_matches[0]  # match the first occurance
        match_type = 'endswith'

    elif len(prefixes_matches):
        matched = prefixes_matches[0]  # match the first occurance
        match_type = 'startswith'

    else:
        err("Did not recogize the application type from the tier name %s" %
             logtier)
        sys.exit(1)

    if matched in tier2glob_equivalents[match_type]:
        matched = tier2glob_equivalents[match_type][matched]

    return match_type, matched

def print_options_summary(options):
    err("---------------------------------------------------------------")
    err("---------------------------- To make these setting default run:")
    err("---------------------------------------------------------------")
    serializable_options = dict(options)
    del serializable_options['log-tiers-hosts']
    del serializable_options['log-tiers-globs']
    del serializable_options['hosts-list']
    del serializable_options['levels-list']
    del serializable_options['start']
    del serializable_options['end']
    del serializable_options['duration']
    del serializable_options['local']
    serializable_options['fp'] = ','.join(serializable_options['fp'])
    serializable_options['fp-exclude'] = \
        ','.join(serializable_options['fp-exclude'])
    serializable_options['re'] = ','.join(serializable_options['re'])
    serializable_options['re-exclude'] = \
        ','.join(serializable_options['re-exclude'])
    err("cat <<'EOF' > $HOME/.hblogrc")
    err(json.dumps(dict(serializable_options),
                        sort_keys=True, indent=4, separators=(',', ': ')))
    err("EOF")
    err("---------------------------------------------------------------")
    err("log-tiers:         %s" % ",".join(options['log-tiers']))
    err("log-tiers-globs:   %s" % ",".join(options['log-tiers-globs'].values()))
    err("hosts-list-size:   %s" % len(options['hosts-list']))
    err("")
    if options['mode'] == 'follow':
        err("type:             %s" % "follow")
    else:
        if options['mode'] == 'details':
            err("type:              %s" % "details")
        else:
            err("type:              %s" % "summary")
        err("start:             %s" % round_to_seconds(options['start']))
        err("end:               %s" % round_to_seconds(options['end']))
        duration = round_to_seconds(options['duration'])
        err("duration:          %s hh:mm:ss" % duration)
    err("")
    err("level:             %s" % options['level'])
    err("sample:            %s" % options['sample'])
    err("fp:                %s" % options['fp'])
    err("fp-exclude:        %s" % options['fp-exclude'])
    err("re:                %s" % options['re'])
    err("re-exclude:        %s" % options['re-exclude'])
    err("---------------------------------------------------------------")


if (__name__ == "__main__"):

    ALL_LEVELS = ["INFO", "DEBUG", "WARN", "ERROR", "FATAL"]

    default_options = {
        "mode": "summary",
        "fp": "",
        "fp-exclude": "",
        "level": "WARN",
        "nowrap": False,
        "re": "",
        "re-exclude": "^\t",  # exclude java stack traces
        "sample": 1.0,
        "verbose": False,
        "tail": None,
        "tail-end": None,
        "log-tiers": [],
    }

    # Load defaults from ~/.hblogrc
    try:
        with open("%s/.hblogrc" % os.getenv("HOME")) as f:
            hblogrc_options = json.load(f)
    except IOError:
        hblogrc_options = {}

    for k, v in hblogrc_options.items():
        default_options[k] = v

    tier_arguments = sorted(set(
                                tier2glob_map['startswith'].keys() +
                                tier2glob_equivalents['startswith'].keys() +
                                tier2glob_map['endswith'].keys() +
                                tier2glob_equivalents['endswith'].keys() +
                                tier2glob_map['re'].keys() +
                                tier2glob_equivalents['re'].keys()))

    num_cols = 3
    step_len = len(tier_arguments) / num_cols
    col_width = 80 / num_cols
    if len(tier_arguments) % num_cols != 0:
        tier_arguments.append(" ")
    raw_cols = [tier_arguments[step_len * i: step_len * (i + 1)] for
                                                        i in range(0, num_cols)]

    final_columns = []
    for line in zip(*raw_cols):
        final_columns.append(" ".join([i.ljust(col_width, " ") for i in line]))

    parser = OptionParser(
        usage="%prog [OPTIONS]... [TIER...] [TIER:HOST...]\n" +
            ("\n  Where TIER is one of:\n\n  %s" %
                                           "\n  ".join(final_columns)))
    parser.description = "hblog - a log paser for clusters"

    parser.add_option("--verbose", "-v", action="store_true",
        default=default_options['verbose'],
        help="print extra information about the state of hblog")

    parser.add_option("--nowrap", "-n", action="store_true",
        default=default_options['nowrap'],
        help="print characters only up to the width of your terminal")


    group = OptionGroup(parser, title="Modes", description=
            "Log lines are \"fingerprinted\", usually able to "
            "assign matching fingerprints to log lines that "
            "differ only by timestamp, specific host names, "
            "or other variables.")

    group.add_option("--summary", dest="mode", const="summary",
        action="store_const",
        help="host-vs-fingerprint frequency table (Default mode)")

    group.add_option("--details", "-d", dest="mode", const="details",
        action="store_const",
        help="print all matching log lines embellished with "
            "hostnames and fingerprints")

    group.add_option("--follow", "-f", dest="mode", const="follow",
        action="store_const",
        help="like --details but streaming, just like 'tail -f'")

    parser.set_defaults(mode=None)
    parser.add_option_group(group)


    group = OptionGroup(parser, title="Select time", description=
            "If time selectors are not supplied, only the last one minute of "
            "logs will be processed.")

    group.add_option("--start", "-s",
        help="process only lines after the time specified                "
            "in format YYYY-MM-DD hh:mm:ss")

    group.add_option("--end", "-e",
        help="process only lines up to the time specified               "
            "in format YYYY-MM-DD hh:mm:ss")

    group.add_option("--tail", "-t",
        default=default_options['tail'],
        help="process only the last X minutes of each log "
            "specified as one of these formats \":sec\", \"min\", \"hour:min\"")

    group.add_option("--tail-end", "-T",
        default=default_options['tail-end'],
        help="process only up to the last X minutes of each log "
            "specified as one of these formats \":sec\", \"min\", \"hour:min\"")

    parser.add_option_group(group)

    group = OptionGroup(parser, "Filters")
    group.add_option("--level", "-l", type='choice',
        choices=ALL_LEVELS, default=default_options['level'],
        help="the log level to filter for (default level: %default)")
    group.add_option("--sample", "-S", type="float",
        default=default_options['sample'],
        help="sampling rate will be achieved by skipping log lines         "
            "(default: 1.0, read all lines)")
    group.add_option("--fp", "-p",
        default=default_options['fp'],
        help="comma-separated list of fingerprints to include")
    group.add_option("--fp-exclude", "-P",
        default=default_options['fp-exclude'],
        help="comma-separated list of fingerprints to exclude")
    group.add_option("--re", "-r",
        default=default_options['re'],
        help="comma-separated list of regex to include (case insensitive)")
    group.add_option("--re-exclude", "-R",
        default=default_options['re-exclude'],
        help="comma-separated list of regex to exclude (case insensitive)")

    group.add_option("--local", action="store_true", default=False,
        help="To test hblog. Connect to localhost. "
        "Read logs from ./var/log/hadoop-example.log")

    parser.add_option_group(group)

    cli_options, cli_args = parser.parse_args()

    options = {}

    for key,val in vars(cli_options).items():
      options[key.replace('_', '-')] = val

    if options['verbose']:
        err("CLI options before processing:")
        err(options)
        err('')
        err("CLI args before processing:")
        err(cli_args)
        err('')

    # Process CLI options with hblog buisness logic
    modes = ['summary', 'follow', 'details']

    if default_options["mode"] not in modes:
        raise HBLogEventsException("Incorrect mode (%s) configured in "
                                   "~/.hblogrc" % default_options["mode"])

    if not options["mode"]:
        options["mode"] = default_options["mode"]

    for i in ['fp', 'fp-exclude']:
        options[i] = options[i].split(',')
        if options[i] == ['']:
            options[i] = []

        for fp in options['fp']:
            if re.match('^[0-9a-f]+$', fp, re.IGNORECASE) is None:
                parser.error("invalid fingerprint: %s" % fp)

    for i in ['re', 're-exclude']:
        options[i] = options[i].split(',')
        if options[i] == ['']:
            options[i] = []
        else:
            [re.compile(r) for r in options[i]]

    for i in ['start', 'end']:
        a = options[i]
        if a:
            if len(a.split(' ')) == 1:
                a = datetime.now().strftime('%Y-%m-%d') + ' ' + a
            options[i] = str_to_time(a + ",000")

    if options['tail']:
        options['start'] = tail_time_from_str(options['tail'])

    if options['tail-end']:
        options['end'] = tail_time_from_str(options['tail-end'])

    if len(cli_args) == 0 and len(default_options['log-tiers']) == 0:
        err("ERROR: You did not provide any arguments")
        parser.print_help()
        err("")
        err("")

    if len(cli_args) > 0:
        options['log-tiers'] = cli_args
    elif 'log-tiers' in default_options and \
                                          len(default_options['log-tiers']) > 0:
        options['log-tiers'] = default_options['log-tiers']
        err("NOTICE: Using ~/hblogrc default tiers: %s" % options['log-tiers'])
    else:
        parser.error("Please specifiy at least one tier. "
            "Multiple tiers can be space-separated.")

    # Default to tailing the last 1 minutes, unless in follow mode
    if options['mode'] == 'follow':
        options['start'] = tail_time_from_str('0:00')
    elif not options['start']:
        options['start'] = tail_time_from_str('1:00')


    options['levels-list'] = ALL_LEVELS[ALL_LEVELS.index(options['level']):]

    if not options['end']:
        options['end'] = datetime.now()

    options['duration'] = options['end'] - options['start']

    options['log-tiers-globs'] = {}
    options['log-tiers-hosts'] = {}

    for logtier in options['log-tiers']:
        if ":" in logtier:
            options['log-tiers-hosts'][logtier] = \
                                            logtier.split(':')[1].split(',')
        else:
            options['log-tiers-hosts'][logtier] = \
                    list_hosts_of_tier('local' if options['local'] else logtier)

    if options['verbose']:
        err('log-tiers is:')
        err(options['log-tiers'])
        err('')
        err('log-tiers-hosts is:')
        err(options['log-tiers-hosts'])
        err('')

    # Resolve log-tiers-globs
    if options['local']:
        for logtier in options['log-tiers']:
            options['log-tiers-globs'][logtier] = \
                tier2glob_map_examples_for_localhost[logtier]
    else:
        for logtier in options['log-tiers']:
            match_type, matched_key = get_matched(logtier.split(':')[0])
            options['log-tiers-globs'][logtier] = \
                                          tier2glob_map[match_type][matched_key]

    if options['verbose']:
        err('log-tiers-globs is:')
        err(options['log-tiers-globs'])
        err('')

    # Get a flat 'hosts-list' for all the hosts we will be operating on
    options['hosts-list'] = \
            list(set(flatten([options['log-tiers-hosts'][t]
                                               for t in options['log-tiers']])))

    if options['verbose']:
        err('hosts-list is:')
        err(options['hosts-list'])
        err('')

    print_options_summary(options)

    if options['verbose']:
        err("CLI options after processing:")
        err(options)
        err(cli_args)

    HBLogEvents(options)
