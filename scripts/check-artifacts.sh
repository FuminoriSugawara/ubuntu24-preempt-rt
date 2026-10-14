#!/usr/bin/env bash
# ビルド用コンテナ内で実行し、成果物と外部モジュール用ヘッダーを検査する。
set -euo pipefail
script_dir=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
# shellcheck source=scripts/kernel-settings.sh
source "$script_dir/kernel-settings.sh"
release=$KERNEL_RELEASE
version=$PACKAGE_VERSION
cd "/workspace/artifacts/$release"
sha256sum -c SHA256SUMS
mkdir -p "/workspace/work/$release"
scratch=$(mktemp -d "/workspace/work/$release/artifact-check.XXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
for kind in "linux-image-$release" "linux-headers-$release" "linux-image-$release-dbg"; do
    deb="${kind}_${version}_amd64.deb"
    [[ $(dpkg-deb -f "$deb" Package) == "$kind" ]]
    [[ $(dpkg-deb -f "$deb" Version) == "$version" ]]
    [[ $(dpkg-deb -f "$deb" Architecture) == amd64 ]]
done
dpkg-deb -x "linux-headers-${release}_${version}_amd64.deb" "$scratch"
dpkg-deb --fsys-tarfile "linux-image-${release}-dbg_${version}_amd64.deb" |
    tar -x -C "$scratch" "./usr/lib/debug/lib/modules/$release/vmlinux"
vmlinux="$scratch/usr/lib/debug/lib/modules/$release/vmlinux"
readelf -SW "$vmlinux" > "$scratch/sections"
grep -E '\.BTF[[:space:]]' "$scratch/sections"
grep -E '\.debug_info[[:space:]]' "$scratch/sections"
python3 - "$vmlinux" "$scratch/sections" <<'PYTHON'
import re, struct, sys
sections = open(sys.argv[2]).read()
match = re.search(r"\.debug_info\s+\S+\s+\S+\s+([0-9a-fA-F]+)", sections)
assert match, "Missing .debug_info section"
with open(sys.argv[1], "rb") as stream:
    stream.seek(int(match.group(1), 16))
    length = struct.unpack("<I", stream.read(4))[0]
    if length == 0xffffffff:
        stream.read(8)
    version = struct.unpack("<H", stream.read(2))[0]
assert version == 5, f"Expected DWARF5, got DWARF{version}"
print("DWARF version: 5")
PYTHON
mkdir "$scratch/module"
cat > "$scratch/module/Makefile" <<'MAKEFILE'
obj-m := rt_header_smoke.o
MAKEFILE
cat > "$scratch/module/rt_header_smoke.c" <<'SOURCE'
#include <linux/module.h>
static int __init smoke_init(void) { return 0; }
static void __exit smoke_exit(void) { }
module_init(smoke_init);
module_exit(smoke_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Build-only verification of exported RT kernel headers");
SOURCE
make -C "$scratch/usr/src/linux-headers-$release" M="$scratch/module" CC=gcc-13 -j2 modules
vermagic=$(modinfo -F vermagic "$scratch/module/rt_header_smoke.ko")
[[ $vermagic == "$release "* ]]
printf 'External module vermagic: %s\nArtifact checks: PASS\n' "$vermagic"
# テストモジュールはロードしない。
