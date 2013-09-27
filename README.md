hblog
=====

log parser for clusters

 - Remote access to logs via a single CLI.
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

    hblog <tier>

    Modes:
     --summary         Host-vs-fingerprint frequency table. Default.

                       Log lines are "fingerprinted", usually able to
                       assign matching fingerprints to log lines that
                       differ only by timestamp, specific host names,
                       or other variable arguments

     --detail, -d      Print all matching log lines embellished with
                       hostnames and fingerprints

     --follow, -f      Like --detail but streaming, just like 'tail -f'

    Select time:
     --start=hh:mm:ss  Process only lines after (or before) the
     --end=hh:mm:ss    specified time. Format is "YYYY-MM-DD hh:mm:ss"

     --tail=hh:mm:ss   Process only the last X minutes of each log
                       (:sec, min, hour:min, hour:min:sec are accepted)

     --tail-end=hh:mm:ss
                       Process only up to the last X minutes of each log
                       (:sec, min, hour:min, hour:min:sec are accepted)

    Filters:
     --sample=X, -p=X  Sampling rate. Done by sikipping log lines.
                       Default: 1.0 (read all lines)

     --level=X         The log level to filter for.  Default level: WARN

     --fp=X            Comma separated list of fingerprints to include
     --supress-fp=X    Comma separated list of fingerprints to exclude

     --re=X            Comma separated list of regex to include
     --supress-re=X    Comma separated list of regex to exclude

    Notes:
    ===================================================================
     - If time selectors are not supplied, only the last 1 minute of
       logs will be processed.


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
    ./bin/hblog.py --local
