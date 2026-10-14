#!/usr/bin/env bash
set -euo pipefail
cd /workspace
# shellcheck source=scripts/kernel-settings.sh
source scripts/kernel-settings.sh
release=$KERNEL_RELEASE
state=/workspace/work/$release
logdir=/workspace/logs/$release
mkdir -p "$state" "$logdir"
exec 9>"$state/build.lock"
flock -n 9 || { echo 'Another build is running' >&2; exit 1; }
exec > >(tee -a "$logdir/build.log") 2>&1
record_exit() {
    local result=$?
    printf '%s\n' "$result" > "$logdir/exit-code"
    exit "$result"
}
trap record_exit EXIT
[[ ! -e artifacts/$release/SHA256SUMS ]] || { echo 'Completed artifacts exist; choose a new BUILD_REVISION' >&2; exit 1; }
date -Is
jobs=${JOBS:-16}
out=$state/output
src=$state/linux-$KERNEL_VERSION
config=/workspace/$BASE_CONFIG
base_hash=$(sha256sum "$config" | cut -d' ' -f1)
input_hash=$(sha256sum kernel.conf "$BASE_CONFIG" Dockerfile scripts/build-in-container.sh scripts/kernel-settings.sh | sha256sum | cut -d' ' -f1)
if [[ -f $state/inputs.sha256 ]]; then
    [[ $(cat "$state/inputs.sha256") == "$input_hash" ]] || { echo 'Build inputs changed; choose a new BUILD_REVISION' >&2; exit 1; }
else
    printf '%s\n' "$input_hash" > "$state/inputs.sha256"
fi
cd downloads
download() {
    local name=$1 url=$2
    if [[ ! -f $name ]]; then
        curl -fL --retry 3 -o "$name.part" "$url"
        mv "$name.part" "$name"
    fi
}
download "$KERNEL_ARCHIVE" "$KERNEL_URL"
download "$RT_PATCH_ARCHIVE" "$RT_PATCH_URL"
printf '%s  %s\n' "$KERNEL_SHA256" "$KERNEL_ARCHIVE" "$RT_PATCH_SHA256" "$RT_PATCH_ARCHIVE" | sha256sum -c -
cd /workspace
if [[ ! -d $src ]]; then
    tar -xJf "downloads/$KERNEL_ARCHIVE" -C "$state"
    xzcat "downloads/$RT_PATCH_ARCHIVE" | patch -d "$src" -p1
    touch "$src/.rt-patch-applied"
fi
[[ -f $src/.rt-patch-applied ]] || { echo 'Incomplete source preparation; use a new work directory' >&2; exit 1; }
mkdir -p "$out"
cd "$src"
if [[ -f $out/base-config.sha256 ]]; then
    [[ $(cat "$out/base-config.sha256") == "$base_hash" ]] || { echo 'Base config changed; use a new work directory' >&2; exit 1; }
else
    cp "$config" "$out/.config"
    scripts/config --file "$out/.config" \
        --enable EXPERT --enable PREEMPT_RT --disable PREEMPT_DYNAMIC \
        --disable PREEMPT_NONE --disable PREEMPT_VOLUNTARY --disable PREEMPT_LAZY \
        --disable DEBUG_INFO_NONE --disable DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT \
        --disable DEBUG_INFO_DWARF4 --enable DEBUG_INFO_DWARF5 \
        --disable DEBUG_INFO_REDUCED --disable DEBUG_INFO_SPLIT \
        --enable DEBUG_INFO_BTF --enable DEBUG_INFO_BTF_MODULES \
        --set-str SYSTEM_TRUSTED_KEYS '' --set-str SYSTEM_REVOCATION_KEYS '' \
        --set-str LOCALVERSION "$KERNEL_LOCALVERSION" --disable LOCALVERSION_AUTO
    printf '%s\n' "$base_hash" > "$out/base-config.sha256"
fi
make O="$out" CC=gcc-13 HOSTCC=gcc-13 olddefconfig
for option in PREEMPT_RT DEBUG_INFO_DWARF5 DEBUG_INFO_BTF DEBUG_INFO_BTF_MODULES; do
    grep -qx "CONFIG_${option}=y" "$out/.config" || { echo "Missing CONFIG_$option" >&2; exit 1; }
done
actual=$(make -s O="$out" CC=gcc-13 HOSTCC=gcc-13 kernelrelease)
[[ $actual == "$release" ]] || { echo "Unexpected release: $actual" >&2; exit 1; }
{
    date -Is
    printf 'Kernel: %s\nBase config SHA256: %s\nJobs: %s\n' "$release" "$base_hash" "$jobs"
    gcc-13 --version
    pahole --version
    dpkg-query -W
} > "$logdir/build-environment.txt"
export KBUILD_BUILD_USER=rt-builder KBUILD_BUILD_HOST=rt-build
export KDEB_PKGVERSION=$PACKAGE_VERSION
export DEB_BUILD_OPTIONS="parallel=$jobs"
export DPKG_DEB_COMPRESSOR_TYPE=zstd DPKG_DEB_COMPRESSOR_LEVEL=3
make O="$out" CC=gcc-13 HOSTCC=gcc-13 -j"$jobs" bindeb-pkg
cd /workspace
dest=artifacts/$release
mkdir -p "$dest"
for pkg in "linux-image-$release" "linux-headers-$release" "linux-image-$release-dbg"; do
    file="$state/${pkg}_${KDEB_PKGVERSION}_amd64.deb"
    [[ -s $file ]] || { echo "Missing $file" >&2; exit 1; }
    dpkg-deb --info "$file"
    cp "$file" "$dest/"
done
cp "$out/.config" "$dest/config-$release"
cp "$out/System.map" "$dest/System.map-$release"
cp "$logdir/build-environment.txt" "$dest/"
cp "$config" "$dest/base.config"
cp kernel.conf scripts/kernel-settings.sh "$dest/"
cp scripts/install-kernel.sh scripts/verify-kernel.sh scripts/sample-memory.sh "$dest/"
cp README.md INSTALL.ja.md "$dest/"
readelf -S "$out/vmlinux" | grep -E '\.BTF|\.debug_info'
cd "$dest"
sha256sum ./*.deb config-* System.map-* base.config build-environment.txt install-kernel.sh verify-kernel.sh sample-memory.sh README.md INSTALL.ja.md kernel.conf kernel-settings.sh > SHA256SUMS
printf 'Build finished: %s\n' "$release"
date -Is
