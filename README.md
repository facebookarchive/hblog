hblog
=====

log parser for clusters

 - Remote access to logs via a single CLI
 - Multi-host summaries of log line frequencies
 - Multi-host realtime tailing (like tail -f)


Supported Log Formats
--------

  - Syslog
  - Log4j
  - Java GC log

For details please see LOGLINE_RE_LIST in hblog/lib/SingleFileLogAccessor.py


Usage
--------

    Usage: hblog [OPTIONS]... [TIER...] [TIER:HOST...]

      Where TIER is one of:

      dfs-nn                     hbase-master-gc            mr-jt
      dfs-nn-gc                  hbase-regionservers        mr-jt-gc
      dfs-slaves                 hbase-regionservers-gc     mr-slaves
      dfs-slaves-gc              hbase-secondary            mr-slaves-gc
      dfs-sn                     hbase-secondary-gc         syslog
      dfs-sn-gc                  hbase-thrift
      hbase-master               hbase-zookeepers

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
                            process only the last X minutes of each log specified
                            as one of these formats ":sec", "min", "hour:min"
        -T TAIL_END, --tail-end=TAIL_END
                            process only up to the last X minutes of each log
                            specified as one of these formats ":sec", "min",
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


Example
--------

    $ hblog --level=INFO mycluster001-hbase-regionservers
    ---------------------------------------------------------------
    ---------------------------- To make these setting default run:
    ---------------------------------------------------------------
    cat <<'EOF' > $HOME/.hblogrc
    {
        "fp": "",
        "fp-exclude": "",
        "level": "WARN",
        "log-tiers": [
            "hbase-regionservers"
        ],
        "mode": "summary",
        "nowrap": true,
        "re": "",
        "re-exclude": "^\t",
        "sample": 1.0,
        "tail": null,
        "tail-end": null,
        "verbose": false
    }
    EOF
    ---------------------------------------------------------------
    log-tiers:         hbase-regionservers
    log-tiers-globs:   /var/log/hadoop/*-HBASE/hbase-hadoop-regionserver-[!g][!c]*
    hosts-list-size:   115

    type:              summary
    start:             2013-10-17 12:34:22
    end:               2013-10-17 12:35:22
    duration:          0:01:00 hh:mm:ss

    level:             WARN
    sample:            1.0
    fp:                []
    fp-exclude:        []
    re:                []
    re-exclude:        ['^\t']
    ---------------------------------------------------------------
    WARNING:root:Connect error on fd 10: ECONNREFUSED
    WARN: HTTP error from hbase999, blacklisting host. Error was HTTP 599: Connection closed.
    WARNING:root:Connect error on fd 11: ECONNREFUSED
    WARN: HTTP error from hbase998, blacklisting host. Error was HTTP 599: Connection closed.
    ---------------------------------------------------------------
    Fingerprint summary:
      count  fingerprint   level        text

       2898  822edf9       WARN   org.apache.hadoop.hbase.regionserver.Store: Not in set org.apache.hadoop.hbase.regionserver.StoreScanner@#
        392  aae50d9       WARN   org.apache.hadoop.hdfs.DFSClient: Null blocks retrieved for : /## offset : #, len : #
        290  d2c8224       WARN   org.apache.hadoop.hbase.regionserver.wal.HLog: IPC Server handler # on # took # ms appending an edit to hlog;
                                  editcount=#, len~=#.# KB
         90  4fcd95b       WARN   org.apache.hadoop.hbase.regionserver.wal.HLog: IPC Server handler # on # took # ms appending an edit to hlog;
                                  editcount=#, len~=#.#
          3  a0e71c9       ERROR  org.apache.hadoop.hbase.regionserver.HRegionServer:
          1  e310f00       WARN   org.apache.hadoop.hbase.regionserver.wal.HLog: IPC Server handler # on # took # ms appending an edit to hlog;
                                  editcount=#, len~=#.# MB
          1  b73e9eb       WARN   org.apache.hadoop.hbase.ipc.HBaseServer: IPC Server handler # on #, call get( ... ) from <<IP>>:#: error: java
                                  .io.IOEx#ption: Could not seek StoreFileScanner[HFileScanner for reader reader=hdfs:/##<<HOST>>:#/## compressi
                                  on=lzo, cacheConf=CacheConfig:enabled [cacheDataOnRead=true] [cacheDataOnWrite=false] [cacheIndex#sOnWrite=fal
                                  se] [cacheBloomsOnWrite=false] [cacheEvictOnClose=false] [cacheCompressed=false], firstKey=#:#@<<HOST>>/## las
                                  tKey=#:#@<<HOST>>/##<<MID>>\x#\x#/## avgKeyLen=#, avgValueLen=#, entries=#, length=#, cur=null] to key #:#@<<H
                                  OST>>/##=#
          1  333fb44       WARN   org.apache.hadoop.hbase.ipc.HBaseServer: IPC Server handler # on #, call get( ... ) from <<IP>>:#: error: java
                                  .io.IOEx#ption: Could not seek StoreFileScanner[HFileScanner for reader reader=hdfs:/##<<HOST>>:#/## compressi
                                  on=lzo, cacheConf=CacheConfig:enabled [cacheDataOnRead=true] [cacheDataOnWrite=false] [cacheIndex#sOnWrite=fal
                                  se] [cacheBloomsOnWrite=false] [cacheEvictOnClose=false] [cacheCompressed=false], firstKey=#:#@<<HOST>>/## las
                                  tKey=#:#@<<HOST>>/## avgKeyLen=#, avgValueLen=#, entries=#, length=#, cur=null] to key #:#@<<HOST>>/##=#
          1  03ebf69       WARN   org.apache.hadoop.hbase.ipc.HBaseServer: IPC Server handler # on #, call get( ... ) from <<IP>>:#: error: java
                                  .io.IOEx#ption: Could not seek StoreFileScanner[HFileScanner for reader reader=hdfs:/##<<HOST>>:#/## compressi
                                  on=lzo, cacheConf=CacheConfig:enabled [cacheDataOnRead=true] [cacheDataOnWrite=false] [cacheIndex#sOnWrite=fal
                                  se] [cacheBloomsOnWrite=false] [cacheEvictOnClose=false] [cacheCompressed=false], firstKey=#:#@<<HOST>>/##<<MI
                                  D>><<MID>>\x#\x#/## lastKey=#:#@<<HOST>>/##<<MID>>\x#\x#/## avgKeyLen=#, avgValueLen=#, entries=#, length=#, c
                                  ur=null] to key #:#@<<HOST>>/##=#
    ---------------------------------------------------------------
    Host sumary:

                        822edf9   aae50d9    d2c8224    4fcd95b    a0e71c9    e310f00    b73e9eb    333fb44    03ebf69
      host001           35
      host002           40
      host003           16         16
      host004           58
      host005           25          9
      host006           15
      host007           14
      host008           49         20
      host009           47
      host010           42
      host011           13
      host012           11         21
      host013           29
      host014           65                                           1                                1
      host015           25
      host016           14          7
      host017                      14
      host018           36         13
      host019                       7
      host020           71
      host021           43
      host022           24
      host023           12         11
      host024           40          4
      host025           22
      host026           39
      host027           50
      host028           20          8
      host029           23
      host030           25
      host031           27
      host032           24
      host033           23
      host034            4
      host035           21
      host036           13         14
      host037           98                   233         71                     1
      host038           68
      host039           21          1
      host040           42         21
      host041           27
      host042           22
      host043           33
      host044           23
      host045            4
      host046           16         15
      host047           73
      host048           14
      host049           12
      host050           41
      host051           29          8
      host052           26
      host053           52
      host054           11
      host055           13
      host056           27
      host057           24
      host058           12
      host059           80          1
      host060            9
      host061           35
      host062           33         18
      host063           42          6
      host064           29
      host065           25
      host066           14
      host067           42
      host068           23
      host069            1          9
      host070           26
      host071           16
      host072           50                                           1                                           1
      host073                       4
      host074           25
      host075           28
      host076           19
      host077           23
      host078           47          5
      host079           31
      host080            3         20
      host081           17         19
      host082           24          5
      host083           33                                           1                     1
      host084           29
      host085           12
      host086           26         13
      host087           61
      host088           18
      host089           12
      host090           37
      host091           38
      host092           11          2
      host093           14          7         57         19
      host094           14
      host095           69
      host096            1         19
      host097           16
      host098           51         12
      host099                      21
      host100                      12
      host101           31         11
      host102           49
      host103           18         19
      host104           13
    ---------------------------------------------------------------

    2013-10-17 12:35:26.776816 BLACKL01 WARN  - Blacklisted 2 hosts (of 115 in this session): set(['host998', 'host999']) - consider adding filters or lowering the sampling rate


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

    cd hblog

    ./sbin/hblogd.py  # in a separate tab or in screen/tmux

    export PATH="$PATH:$(pwd)/bin"  # for list_hosts_of_tier.sh
    ./bin/hblog.py --local  --start '2011-03-27 12:48:18' nn
    ./bin/hblog.py --local  --start '2011-03-27 12:48:18' nn-gc
    ./bin/hblog.py --local  --start '2011-03-27 12:48:18' syslog
