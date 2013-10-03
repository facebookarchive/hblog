#!/bin/bash

set -e
set -u

function usage(){
  echo "Usage: list_hosts_of_tier <name>"
}

if [ "$#" != "1" ]; then
  usage
  exit
fi

function get_hosts(){
  tier=$1

  # Dummy hostname generator, intead you would want to generate
  # hosts based on $tier
  out="$(echo localhost.searchname.com; echo localhost.searchname.com)"

  exit_status=$?
  echo "$out"
  exit $exit_status
}

tier=$1

case $tier in
nn)
  out="$(get_hosts $cellname-dfs-nn)"
  ;;
sn)
  out="$(get_hosts $cellname-dfs-sn)"
  ;;
master)
  out="$(get_hosts $cellname-hbase-master)"
  ;;
secondary)
  out="$(get_hosts $cellname-hbase-secondary)"
  ;;
regionservers)
  out="$(get_hosts $cellname-hbase-regionservers)"
  ;;
dfs-slaves)
  out="$(get_hosts $cellname-dfs-slaves)"
  ;;
hbase-thrift)
  out="$(get_hosts $cellname-hbase-thrift)"
  ;;
hbase-zookeepers)
  out="$(get_hosts $cellname-hbase-zookeepers)"
  ;;
jt)
  out="$(get_hosts $cellname-mr-jt)"
  ;;
mr-slaves)
  out="$(get_hosts $cellname-mr-slaves)"
  ;;
zookeepers)
  out="$(get_hosts $cellname-zookeepers)"
  ;;
*-syslog)
  cellname="$(echo "$tier" | sed 's|-syslog$||')"
  out="$(get_hosts $cellname-hbase-regionservers)"
  out="$out\n$(get_hosts $cellname-controllers)"
  ;;
syslog)
  out="$(get_hosts $cellname-hbase-regionservers)"
  out="$out\n$(get_hosts $cellname-controllers)"
  ;;
*)

  out="$(get_hosts $tier)"
  ;;
esac

echo -e "$out" | sed 's|.searchname.com||'
