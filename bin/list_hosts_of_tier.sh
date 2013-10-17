#!/bin/bash

# Prefix all global function and variable names because this will be sourced

function lhot_usage(){
  echo "Usage: list_hosts_of_tier <name>"
  echo "       list_hosts_of_tier --list-tiers"
  echo
  echo "NOTE: This script, for some arguments assumes that "
  echo "      \$cellname environmental variable is set."
  echo "      E.g.: export cellname=cluster001"
}

function lhot_list_all_tiers(){
    local matches

    # Shorthand
    local matches_endswith="$(echo \
                                    dfs-nn \
                                    dfs-sn \
                                    dfs-slaves \
                                    hbase-regionservers \
                                    hbase-master \
                                    hbase-secondary \
                                    hbase-thrift \
                                    mr-jt \
                                    mr-slaves \
                                    zookeepers \
                                    | sed 's/ /\n/g')"
    matches="$matches\n$matches_endswith"
    matches="$matches\nsyslog"
    matches="$matches\ngc"

    # Java GC and syslog shorthand
    matches="$(
    echo -e "$matches_endswith" | while read ending; do
        echo "$ending-syslog"
        echo "$ending-gc"
    done)\n$matches"

    # hbase cells tiers + Java GC + syslog
    hbase_cells="cluster001\ncluster002\ncluster003"
    matches="$(
    echo -e "$hbase_cells" | while read cell; do
      echo -e "$matches_endswith" | while read ending; do
        echo "$cell-$ending"
        echo "$cell-$ending-gc"
        echo "$cell-$ending-syslog"
      done
    done)\n$matches"

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
  dfs-nn|dfs-nn-gc|dfs-nn-syslog )
    out="$(lhot_get_hosts $cellname-dfs-nn)"
    ;;
  dfs-sn|dfs-sn-gc|dfs-sn-syslog )
    out="$(lhot_get_hosts $cellname-dfs-sn)"
    ;;
  hbase-master|hbase-master-gc|hbase-master-syslog )
    out="$(lhot_get_hosts $cellname-hbase-master)"
    ;;
  hbase-secondary|hbase-secondary-gc|hbase-secondary-syslog )
    out="$(lhot_get_hosts $cellname-hbase-secondary)"
    ;;
  hbase-regionservers|hbase-regionservers-gc|hbase-regionservers-syslog )
    out="$(lhot_get_hosts $cellname-hbase-regionservers)"
    ;;
  dfs-slaves|dfs-slaves-gc|dfs-slaves-syslog )
    out="$(lhot_get_hosts $cellname-dfs-slaves)"
    ;;
  hbase-thrift|hbase-thrift-gc|hbase-thrift-syslog )
    out="$(lhot_get_hosts $cellname-hbase-thrift)"
    ;;
  mr-jt|mr-jt-gc|mr-jt-syslog )
    out="$(lhot_get_hosts $cellname-mr-jt)"
    ;;
  mr-slaves|mr-slaves-gc|mr-slaves-syslog )
    out="$(lhot_get_hosts $cellname-mr-slaves)"
    ;;
  zookeepers|zookeepers-gc|zookeepers-syslog )
    out="$(lhot_get_hosts $cellname-zookeepers)"
    ;;
  *-gc)
    tier1="$(echo "$tier" | sed 's|-gc$||')"
    out="$(lhot_get_hosts $tier1)"
    ;;
  *-syslog)
    tier1="$(echo "$tier" | sed 's|-syslog$||')"
    out="$(lhot_get_hosts $tier1)"
    ;;
  syslog)
    out="$(lhot_get_hosts $cellname-hbase-regionservers)"
    out="$out\n$(lhot_get_hosts $cellname-controllers)"
    ;;
  gc)
    out="$(lhot_get_hosts $cellname-hbase-regionservers)"
    out="$out\n$(lhot_get_hosts $cellname-controllers)"
    ;;
  *)
    if host $tier &> /dev/null; then
      out="$(lhot_get_hosts $tier)"
    else
      echo "Can't recognize tier $tier"
      return 2
    fi
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
