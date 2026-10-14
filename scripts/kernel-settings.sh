#!/usr/bin/env bash
# sourceして使う。リポジトリと成果物の両方の配置を扱う。
settings_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [[ -f $settings_dir/kernel.conf ]]; then
    settings_file=$settings_dir/kernel.conf
else
    settings_file=$settings_dir/../kernel.conf
fi
# shellcheck disable=SC1090
source "$settings_file"
settings_error() { echo "Invalid kernel.conf: $1" >&2; return 1; }
[[ ${KERNEL_VERSION:-} =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]] || { settings_error KERNEL_VERSION; return 1; }
[[ ${RT_VERSION:-} =~ ^rt[0-9]+$ ]] || { settings_error RT_VERSION; return 1; }
[[ ${BUILD_REVISION:-} =~ ^[1-9][0-9]*$ ]] || { settings_error BUILD_REVISION; return 1; }
for checksum in "${KERNEL_SHA256:-}" "${RT_PATCH_SHA256:-}"; do
    [[ $checksum =~ ^[a-f0-9]{64}$ ]] || { settings_error SHA256; return 1; }
done
for url in "${KERNEL_URL:-}" "${RT_PATCH_URL:-}"; do
    [[ $url == https://* && $url != *[[:space:]]* ]] || { settings_error URL; return 1; }
done
[[ ${BASE_CONFIG:-} == configs/* && $BASE_CONFIG != *..* && $BASE_CONFIG =~ ^[a-zA-Z0-9_./-]+$ ]] || { settings_error BASE_CONFIG; return 1; }
KERNEL_LOCALVERSION=
if (( BUILD_REVISION > 1 )); then
    KERNEL_LOCALVERSION=-build${BUILD_REVISION}
fi
KERNEL_RELEASE=${KERNEL_VERSION}-${RT_VERSION}${KERNEL_LOCALVERSION}
PACKAGE_VERSION=${KERNEL_VERSION}-${RT_VERSION}-${BUILD_REVISION}
KERNEL_ARCHIVE=linux-${KERNEL_VERSION}.tar.xz
RT_PATCH_ARCHIVE=patch-${KERNEL_VERSION}-${RT_VERSION}.patch.xz
DEFAULT_CONTAINER_NAME=ubuntu-preempt-rt-${KERNEL_RELEASE}
export KERNEL_VERSION RT_VERSION BUILD_REVISION KERNEL_URL RT_PATCH_URL
export KERNEL_SHA256 RT_PATCH_SHA256 BASE_CONFIG KERNEL_RELEASE PACKAGE_VERSION
export KERNEL_ARCHIVE RT_PATCH_ARCHIVE DEFAULT_CONTAINER_NAME KERNEL_LOCALVERSION
