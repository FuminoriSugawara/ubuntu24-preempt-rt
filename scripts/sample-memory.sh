#!/usr/bin/env bash
# CSV 1 行分を標準出力に出す。--header は列名を出す。
set -euo pipefail
if [[ ${1:-} == --header ]]; then
    echo 'time,host,kernel,uptime_seconds,mem_available_kib,slab_kib,sreclaimable_kib,sunreclaim_kib'
    exit 0
fi
awk -v time="$(date -Is)" -v host="${MEMORY_LABEL:-target}" -v kernel="$(uname -r)" \
    -v uptime="$(cut -d' ' -f1 /proc/uptime)" '
    /^(MemAvailable|Slab|SReclaimable|SUnreclaim):/ {v[$1]=$2}
    END {printf "%s,%s,%s,%s,%s,%s,%s,%s\n", time,host,kernel,uptime,v["MemAvailable:"],v["Slab:"],v["SReclaimable:"],v["SUnreclaim:"]}
' /proc/meminfo
