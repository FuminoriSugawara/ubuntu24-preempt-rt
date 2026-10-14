#!/usr/bin/env bash
# 対象機で実行する。引数なしでは読み取り確認だけを行う。
set -euo pipefail
script_dir=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
# shellcheck source=scripts/kernel-settings.sh
source "$script_dir/kernel-settings.sh"
release=$KERNEL_RELEASE
version=$PACKAGE_VERSION
mode=check
with_debug=0
for arg in "$@"; do
    case "$arg" in
        --check) mode=check ;;
        --install) mode=install ;;
        --with-debug) with_debug=1 ;;
        *) echo "Usage: $0 [--check|--install] [--with-debug]" >&2; exit 2 ;;
    esac
done
cd "$(dirname "$(readlink -f "$0")")"
[[ $(dpkg --print-architecture) == amd64 ]] || { echo 'amd64 required' >&2; exit 1; }
# shellcheck disable=SC1091
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || { echo 'Ubuntu 24.04 required' >&2; exit 1; }
sha256sum -c SHA256SUMS
packages=("./linux-image-${release}_${version}_amd64.deb" "./linux-headers-${release}_${version}_amd64.deb")
(( ! with_debug )) || packages+=("./linux-image-${release}-dbg_${version}_amd64.deb")
required_kib=0
for file in "${packages[@]}"; do
    [[ $(dpkg-deb -f "$file" Architecture) == amd64 ]]
    [[ $(dpkg-deb -f "$file" Version) == "$version" ]]
    size=$(dpkg-deb -f "$file" Installed-Size)
    required_kib=$((required_kib + size))
    dpkg-deb -W "$file"
done
available=$(df -Pk /usr | awk 'END {print $4}')
(( available > required_kib + 2097152 )) || { echo 'Insufficient /usr space (including 2 GiB margin)' >&2; exit 1; }
boot_available=$(df -Pk /boot | awk 'END {print $4}')
(( boot_available > 1048576 )) || { echo 'At least 1 GiB free in /boot required' >&2; exit 1; }
if [[ -d /sys/firmware/efi ]]; then
    command -v mokutil >/dev/null || { echo 'Install mokutil to check Secure Boot' >&2; exit 1; }
    state=$(LC_ALL=C mokutil --sb-state)
    echo "$state"
    [[ $state == *'SecureBoot disabled'* ]] || { echo 'This unsigned kernel requires Secure Boot disabled or a separate signing procedure' >&2; exit 1; }
fi
command -v update-initramfs >/dev/null
command -v update-grub >/dev/null
printf 'Current kernel: %s\nNew kernel: %s\n' "$(uname -r)" "$release"
if command -v dkms >/dev/null; then dkms status; fi
if [[ $mode == check ]]; then
    echo 'Check complete. No packages installed. Use sudo bash install-kernel.sh --install [--with-debug].'
    exit 0
fi
[[ $EUID == 0 ]] || { echo 'Run --install with sudo' >&2; exit 1; }
# 完全一致した image/headers と、指定時だけ dbg を導入する。linux-libc-dev は対象外。
apt-get install "${packages[@]}"
if [[ -f /boot/initrd.img-$release ]]; then
    update-initramfs -u -k "$release"
else
    update-initramfs -c -k "$release"
fi
update-grub
[[ -s /boot/vmlinuz-$release && -s /boot/initrd.img-$release ]]
printf 'Installed %s. No reboot performed. Old kernels are retained.\n' "$release"
echo 'GRUB may select the new kernel by default on the next boot. Check drivers and arrange console access before reboot.'
