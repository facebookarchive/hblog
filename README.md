hblog
=====

log parser for clusters

 - Remote access to logs via a single CLI
 - Multi-host summaries of log line frequencies
 - Muiti-host realtime tailing (like tail -f)


Example
--------

    $ hblog --level=INFO mycluster001-hbase-regionservers
    ---------------------------------------------------------------
    logs-tier:            mycluster001-hbase-regionservers
    level:                INFO
    start:                2013-05-24 12:08:00
    end:                  2013-05-24 12:18:00
    duration:             0:10:00 hh:mm:ss
    fingerprints:         None
    supress fingerprints: None
    regex:                []
    supress regex:        []
    maxmline:             20
    maxgb:                5
    logpath:              /usr/local/hadoop/logs/*-HBASE/hbase-hadoop-regionserver*
    ---------------------------------------------------------------

    Fingerprint summary:
      count  fingerprint   level        text

      11947  uY07aYUl      WARN   org.apache.hadoop.hbase.regionserver.wal.HLog: HDFS pipeline error detected. Found # replic
                                  as but expecting # replicas.  Requesting close of hlog.
       3288  5sPw6+0U      INFO   org.apache.hadoop.hdfs.DFSClient: Sending a heartbeat packet for block blk_#_#
       2748  zIfi4NUX      INFO   org.apache.hadoop.hdfs.DFSClient: Sending a heartbeat packet for block blk_-#_#
       1050  AZ2P9oRA      DEBUG  org.apache.hadoop.hbase.io.hfile.LruBlockCache: Cache Stats: Sizes: Total=#.#MB ( ... ), Co
                                  unts: Blocks=#, Access=#, Hit=#, Miss=#, cachingAccesses=#, cachingHits=#, Evictions=#, Evi
                                  cted=#, Ratios: Hit Ratio=#.#%, Miss Ratio=#.#%, Evicted/##=#.#
         80  IaEUxbWa      DEBUG  org.apache.hadoop.hbase.io.hfile.LruBlockCache: Cache Stats: Sizes: Total=#.#MB ( ... ), Co
                                  unts: Blocks=#, Access=#, Hit=#, Miss=#, cachingAccesses=#, cachingHits=#, Evictions=#, Evi
                                  cted=#, Ratios: Hit Ratio=#.#%, Miss Ratio=#.#%, Evicted/##=NaN
         60  KXTJ7dfl      DEBUG  org.apache.hadoop.hbase.io.hfile.LruBlockCache: Cache Stats: Sizes: Total=#.#MB ( ... ), Co
                                  unts: Blocks=#, Access=#, Hit=#, Miss=#, cachingAccesses=#, cachingHits=#, Evictions=#, Evi
                                  cted=#, Ratios: Hit Ratio=NaN%, Miss Ratio=NaN%, Evicted/##=NaN
         34  23xdItOY      DEBUG  org.apache.hadoop.hbase.regionserver.LogRoller: Hlog roll period #ms elapsed


    Host sumary:

                        uY07aYUl   5sPw6+0U   zIfi4NUX   AZ2P9oRA   IaEUxbWa   KXTJ7dfl   23xdItOY

              host001                    50                    10
              host002                    50                    10
              host003                               50                    10                     1
              host004                               50         10
              host005                    50                    10
              host006                               50         10
              host007                               50         10
              host008                    50                    10
              host009                               50         10
              host010                               50         10
              host011                    50                    10
              host012        598                    50         10
              host013        599                    50         10
              host014                               50         10
              host015        599                    50                               10
              host016        598                    50         10
              host017                    50                    10
              host018                    50                    10
              host019                               50         10
              host020        599         50                               10

Usage
--------

    hblog.py <tier>[,tier ...] [options]

    hblog - a log paser for clusters

    Options:
    -h, --help            show this help message and exit
    -v, --verbose         print extra information about the state of hblog
    -n, --nowrap          print characters only up to the width of your terminal

    Modes:
      Log lines are "fingerprinted", usually able to assign matching
      fingerprints to log lines that differ only by timestamp, specific host
      names, or other variables.

      --summary           host-vs-fingerprint frequency table (Default mode)
      -d, --details       print all matching log lines embellished with
                          hostnames and fingerprints
      -f, --follow        like --details but streaming, just like 'tail -f'

    Select time:
      If time selectors are not supplied, only the last one minute of logs
      will be processed.

      -s START, --start=START
                          process only lines after the time specified
                          in format YYYY-MM-DD hh:mm:ss
      -e END, --end=END   process only lines up to the time specified
                          in format YYYY-MM-DD hh:mm:ss
      -t TAIL, --tail=TAIL
                          process only the last X minutes of each logspecified
                          as one of these formats ":sec", "min", "hour:min"
      -T TAIL_END, --tail-end=TAIL_END
                          process only up to the last X minutes of each
                          logspecified as one of these formats ":sec", "min",
                          "hour:min"

    Filters:
      -l LEVEL, --level=LEVEL
                          the log level to filter for (default level: WARN)
      -S SAMPLE, --sample=SAMPLE
                          sampling rate will be achieved by skipping log lines
                          (default: 1.0, read all lines)
      -p FP, --fp=FP      comma-separated list of fingerprints to include
      -P FP_EXCLUDE, --fp-exclude=FP_EXCLUDE
                          comma-separated list of fingerprints to exclude
      -r RE, --re=RE      comma-separated list of regex to include (case
                          insensitive)
      -R RE_EXCLUDE, --re-exclude=RE_EXCLUDE
                          comma-separated list of regex to exclude (case
                          insensitive)
      --local             To test hblog. Connect to localhost. Read logs from
                          ./var/log/hadoop-example.log


Open source license
--------
This project is licensed under the Apache 2.0 license


Requires
--------

 - tornado 3.0.1 (https://github.com/facebook/tornado/tree/v3.0.1)


Setup
--------

    git clone https://github.com/facebook/hblog.git
    cd hblog
    git submodule init tornado/
    git submodule update tornado/


Run
----

    ./sbin/hblogd.py
    ./bin/hblog.py --local --start '2011-03-27 13:48:00'
