#!/usr/bin/env bash
# Ubuntu 24.04 コンテナでデバッグ情報付き RT カーネルをビルドする。
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
# shellcheck source=scripts/kernel-settings.sh
source scripts/kernel-settings.sh
jobs=${JOBS:-16}
memory=${MEMORY:-24g}
name=${CONTAINER_NAME:-$DEFAULT_CONTAINER_NAME}
[[ $jobs =~ ^[1-9][0-9]*$ ]] || { echo 'JOBS must be a positive integer' >&2; exit 1; }
[[ $(uname -m) == x86_64 ]] || { echo 'x86_64 host required' >&2; exit 1; }
[[ -s $BASE_CONFIG ]]
[[ ! -e artifacts/$KERNEL_RELEASE/SHA256SUMS ]] || { echo "Artifacts already exist; choose a new BUILD_REVISION" >&2; exit 1; }
mkdir -p downloads "work/$KERNEL_RELEASE" artifacts "logs/$KERNEL_RELEASE"
docker build -t rt-kernel-builder:noble .
docker image inspect rt-kernel-builder:noble > "logs/$KERNEL_RELEASE/container-image.json"
# コンテナを残し、SSH 切断後も処理とログを保持する。
docker run -d --name "$name" --cpus "$jobs" --memory "$memory" --memory-swap "$memory" \
    --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
    -e HOME=/tmp -e JOBS="$jobs" -v "$PWD:/workspace" -w /workspace \
    rt-kernel-builder:noble bash scripts/build-in-container.sh
printf 'Progress: docker logs -f %s\nResult: docker inspect --format {{.State.ExitCode}} %s\n' "$name" "$name"
