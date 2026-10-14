#!/usr/bin/env python3
"""ユーザー用systemdタイマーを登録する。カーネルの導入は行わない。"""
import argparse
from pathlib import Path
import re
import shutil
import subprocess


def quoted(value):
    if any(c in value for c in '\n\r\0'):
        raise ValueError('Newlines and NUL are not allowed')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--branch', default='main')
    parser.add_argument('--calendar', default='Sun *-*-* 03:00:00 Asia/Tokyo')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repo):
        parser.error('Expected OWNER/REPO')
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', args.branch):
        parser.error('Invalid branch')
    subprocess.run(['systemd-analyze', 'calendar', args.calendar], check=True)
    root = Path(__file__).resolve().parent.parent
    config = Path.home() / '.config/rt-kernel-release'
    units = Path.home() / '.config/systemd/user'
    lib = Path.home() / '.local/lib/rt-kernel-release'
    for path in [config, units, lib]:
        path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / 'scripts/run-scheduled-release.sh', lib / 'run.sh')
    env = config / 'environment'
    env.write_text(f'RT_REPOSITORY={quoted(args.repo)}\nRT_BRANCH={quoted(args.branch)}\n'
                   f'RT_CHECKOUT={quoted(str(args.directory.expanduser().resolve()))}\nJOBS=16\nMEMORY=24g\n')
    env.chmod(0o600)
    (units / 'rt-kernel-release.service').write_text(
        '[Unit]\nDescription=Build and publish the configured PREEMPT_RT kernel\n'
        '[Service]\nType=oneshot\n'
        'EnvironmentFile=%h/.config/rt-kernel-release/environment\n'
        f'ExecStart=/bin/bash {quoted(str(lib / "run.sh"))}\n'
        'TimeoutStartSec=infinity\nUMask=0022\n')
    (units / 'rt-kernel-release.timer').write_text(
        '[Unit]\nDescription=Periodic PREEMPT_RT kernel release\n'
        f'[Timer]\nOnCalendar={args.calendar}\nPersistent=true\nAccuracySec=1min\n'
        '[Install]\nWantedBy=timers.target\n')
    subprocess.run(['systemd-analyze', '--user', 'verify', str(units / 'rt-kernel-release.service'), str(units / 'rt-kernel-release.timer')], check=True)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', '--now', 'rt-kernel-release.timer'], check=True)
    subprocess.run(['systemctl', '--user', 'list-timers', 'rt-kernel-release.timer', '--no-pager'], check=True)


if __name__ == '__main__':
    main()
