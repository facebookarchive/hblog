#!/bin/bash

# Prefix all global function and variable names because this will be sourced

function lhot_usage(){
  echo "Usage: list_hosts_of_tier <name>"
  echo "       list_hosts_of_tier --list-tiers"
}

function lhot_list_all_tiers(){
    local matches

    # Shorthand
    local shorthand_matches="$(echo nn                \
                                    jt                \
                                    sn                \
                                    syslog            \
                                    master            \
                                    mr-slaves         \
                                    secondary         \
                                    zookeepers        \
                                    dfs-slaves        \
                                    hbase-thrift      \
                                    regionservers     \
                                    hbase-zookeepers  | sed 's/ /\n/g')"

    local shorthand_re_list="$(echo -e "$shorthand_matches" | \
                                            while read m; do echo "$m$"; done)"
    matches="$matches\n$shorthand_matches"

    # remove empty lines and echo
    echo -e "$matches" | sed -e '/^[[:space:]]*$/d'
}


# Plumbing
function lhot_get_hosts(){
  tier=$1

  # Dummy hostname generator, intead you would want to generate
  # hosts based on $tier
  out="$(echo localhost.searchname.com; echo localhost.searchname.com)"
  exit_status=$?
  echo "$out"
  exit $exit_status
}


# Porcelain
function lhot_list_hosts_porcelain(){
  tier=$1

  case $tier in
  local)
    out="localhost"
    ;;
  nn)
    out="$(lhot_get_hosts $cellname-dfs-nn)"
    ;;
  sn)
    out="$(lhot_get_hosts $cellname-dfs-sn)"
    ;;
  master)
    out="$(lhot_get_hosts $cellname-hbase-master)"
    ;;
  secondary)
    out="$(lhot_get_hosts $cellname-hbase-secondary)"
    ;;
  regionservers)
    out="$(lhot_get_hosts $cellname-hbase-regionservers)"
    ;;
  dfs-slaves)
    out="$(lhot_get_hosts $cellname-dfs-slaves)"
    ;;
  hbase-thrift)
    out="$(lhot_get_hosts $cellname-hbase-thrift)"
    ;;
  hbase-zookeepers)
    out="$(lhot_get_hosts $cellname-hbase-zookeepers)"
    ;;
  jt)
    out="$(lhot_get_hosts $cellname-mr-jt)"
    ;;
  mr-slaves)
    out="$(lhot_get_hosts $cellname-mr-slaves)"
    ;;
  zookeepers)
    out="$(lhot_get_hosts $cellname-zookeepers)"
    ;;
  *-syslog)
    cellname="$(echo "$tier" | sed 's|-syslog$||')"
    out="$(lhot_get_hosts $cellname-hbase-regionservers)"
    out="$out\n$(lhot_get_hosts $cellname-controllers)"
    ;;
  syslog)
    out="$(lhot_get_hosts $cellname-hbase-regionservers)"
    out="$out\n$(lhot_get_hosts $cellname-controllers)"
    ;;
  *)
    out="$(lhot_get_hosts $tier)"
    ;;
  esac

  if [ $? -eq 0 -a "x$out" != x ]; then
    echo -e "$out"
  else
    return $?
  fi
}


lhot_was_sourced=1
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  lhot_was_sourced=""
fi

if [ "x$lhot_was_sourced" = x ]; then
  # Script is not sourced

  set -e
  set -u

  if [ "$#" != "1" ]; then
    lhot_usage
    exit
  fi

  if echo $@ | grep -q "\-\-list-tiers"; then
    lhot_list_all_tiers
    exit
  fi

  tier=$1
  lhot_list_hosts_porcelain $tier
fi
