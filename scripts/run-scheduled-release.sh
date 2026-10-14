#!/usr/bin/env bash
# systemdのEnvironmentFileから専用チェックアウトの場所を受け取る。
set -euo pipefail
: "${RT_CHECKOUT:?}" "${RT_REPOSITORY:?}" "${RT_BRANCH:?}"
mkdir -p "$HOME/.local/state/rt-kernel-release"
exec 8>"$HOME/.local/state/rt-kernel-release/schedule.lock"
flock -n 8 || { echo 'Another scheduled release is running'; exit 0; }
export GIT_TERMINAL_PROMPT=0 GH_PROMPT_DISABLED=1 PYTHONUNBUFFERED=1
# トークンを引数やファイルへ書き出さず、既存のgh認証を使用する。
git_auth() { git -c credential.helper= -c 'credential.helper=!gh auth git-credential' "$@"; }
if [[ ! -d $RT_CHECKOUT/.git ]]; then
    git_auth clone --branch "$RT_BRANCH" "https://github.com/$RT_REPOSITORY.git" "$RT_CHECKOUT"
fi
cd "$RT_CHECKOUT"
[[ -z $(git status --porcelain) ]] || { echo 'Dedicated checkout has local changes' >&2; exit 1; }
[[ $(git remote get-url origin) == "https://github.com/$RT_REPOSITORY.git" ]] || { echo 'Unexpected origin' >&2; exit 1; }
[[ $(git branch --show-current) == "$RT_BRANCH" ]] || { echo 'Unexpected branch' >&2; exit 1; }
git_auth fetch origin "$RT_BRANCH"
git merge --ff-only "origin/$RT_BRANCH"
exec python3 scripts/release-kernel.py --repo "$RT_REPOSITORY"
