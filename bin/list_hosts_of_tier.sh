#!/bin/bash

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

function usage(){
  echo "Usage: list_hosts_of_tier <name>"
}

if [ "$#" != "1" ]; then
  usage
  exit
fi

tier=$1
out=$(echo localhost.searchname.com; echo localhost.searchname.com)
exit_status=$?

echo -e "$out" | sed 's|.searchname.com||'
exit $exit_status
