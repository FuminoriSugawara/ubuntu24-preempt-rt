#!/usr/bin/env bash
# 再起動後の対象機で、カーネル・デバッグ設定・メモリを確認する。
set -euo pipefail
script_dir=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
# shellcheck source=scripts/kernel-settings.sh
source "$script_dir/kernel-settings.sh"
expected=$KERNEL_RELEASE
actual=$(uname -r)
[[ $actual == "$expected" ]] || { echo "Expected $expected, running $actual" >&2; exit 1; }
for option in PREEMPT_RT DEBUG_INFO_DWARF5 DEBUG_INFO_BTF DEBUG_INFO_BTF_MODULES; do
    grep -qx "CONFIG_${option}=y" "/boot/config-$actual" || { echo "Missing CONFIG_$option" >&2; exit 1; }
done
[[ $(cat /sys/kernel/realtime) == 1 ]]
[[ -s /sys/kernel/btf/vmlinux ]]
uname -a
printf 'PREEMPT_RT / DWARF5 / BTF / module BTF: OK\n'
if [[ -s /usr/lib/debug/boot/vmlinux-$actual ]]; then
    echo 'Separate vmlinux debug symbols: installed'
else
    echo 'Separate vmlinux debug symbols: not installed (optional --with-debug package)'
fi
cat /proc/cmdline
grep -E 'MemAvailable|Slab:|SReclaimable|SUnreclaim' /proc/meminfo
if command -v dkms >/dev/null; then dkms status; fi
