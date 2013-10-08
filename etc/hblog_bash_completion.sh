source list_hosts_of_tier.sh  # provides: list_all_tiers, list_hosts_porcelain

case "$COMP_WORDBREAKS" in
  (*:*) true ; ;;
  (*) COMP_WORDBREAKS="$COMP_WORDBREAKS:" ; ;;
esac

# Usage: _hblog_comp_reply <completion_list> [prefix]
#
# Options:
#        completion_list           - Newline separated list of words
#        prefix                    - Add a prefix to all reply items
_hblog_comp_reply ()
{
  local IFS=$'\n'
  local i=0
  for x in $1; do
    COMPREPLY[i++]="$2$x "
  done
}

_hblog_tab_complete()
{
    local curw=${COMP_WORDS[COMP_CWORD]}

    local matches=""
    local prefix=""

    if echo "$curw" | grep -q ":"; then
      local curw_precol="$(echo "$curw" | awk -F: '{print $1}')"
      local curw_postcol="$(echo "$curw" | awk -F: '{print $2}')"

      if echo "$curw_postcol" | grep -q ","; then
        prefix="$(echo "$curw_postcol" | awk -F, '{$(NF--)=""; print}' | sed 's| |,|g')"
        local curw_postcol="$(echo "$curw" | awk -F, '{print $NF}')"
      fi

      local hosts="$(lhot_list_hosts_porcelain $curw_precol | sort | uniq)"

      # in the :host case all previous matches don't matter
      matches="$(echo -e "$hosts" | grep ^$curw_postcol)"

    else
      matches="$(lhot_list_all_tiers | grep ^$curw)"
    fi

    # remove duplicates
    matches="$(echo -e "$matches" | grep -Pv '^$')"

    _hblog_comp_reply "$matches" "$prefix"

    return
}

complete -o bashdefault -o default -o nospace -F _hblog_tab_complete hblog
