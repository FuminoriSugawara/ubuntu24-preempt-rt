#!/usr/bin/env python3
"""指定版をビルド・検査し、検証済みのファイルだけをReleaseへ配置する。"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent


def run(*args, capture=False, cwd=None):
    result = subprocess.run(args, cwd=cwd or ROOT, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def settings():
    raw = run('bash', '-euc', 'source scripts/kernel-settings.sh; '
              'python3 -c \'import os,json; print(json.dumps(dict(os.environ)))\'', capture=True)
    return json.loads(raw)


def get_release(repo, tag):
    result = subprocess.run(['gh', 'api', f'repos/{repo}/releases/tags/{tag}'],
                            text=True, capture_output=True, cwd=ROOT)
    if result.returncode:
        if '(HTTP 404)' in result.stderr:
            # タグ未作成の下書きは /releases/tags では取得できない。
            pages = json.loads(run('gh', 'api', f'repos/{repo}/releases',
                                   '--paginate', '--slurp', capture=True))
            matches = [item for page in pages for item in page if item['tag_name'] == tag]
            if len(matches) > 1:
                raise RuntimeError('Multiple releases use this tag')
            return matches[0] if matches else None
        raise RuntimeError(f'Release lookup failed: {result.stderr.strip()}')
    return json.loads(result.stdout)


def wait_for_release(repo, tag):
    # 作成直後は一覧への反映が遅れる場合がある。
    for delay in (0, 1, 2, 4, 8, 15):
        if delay:
            time.sleep(delay)
        release = get_release(repo, tag)
        if release is not None:
            return release
    raise RuntimeError('Created release is not yet visible; retry to resume the draft')


def ensure_target(release, commit):
    if release['target_commitish'] != commit:
        raise RuntimeError('This version belongs to another commit; change BUILD_REVISION')


def asset_matches(asset, path):
    return (asset.get('state') == 'uploaded' and asset.get('size') == path.stat().st_size
            and asset.get('digest') == 'sha256:' + digest(path))


def build(cfg):
    release = cfg['KERNEL_RELEASE']
    dest = ROOT / 'artifacts' / release
    if (dest / 'SHA256SUMS').exists():
        return dest
    name = cfg['DEFAULT_CONTAINER_NAME']
    names = run('docker', 'ps', '-a', '--format', '{{.Names}}', capture=True).splitlines()
    if name in names:
        mount = run('docker', 'inspect', '--format',
                    '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}',
                    name, capture=True)
        if mount != str(ROOT):
            raise RuntimeError('Container belongs to another checkout; refusing to reuse it')
        status = run('docker', 'inspect', '--format', '{{.State.Status}}', name, capture=True)
        if status == 'exited':
            run('docker', 'start', name)
        elif status != 'running':
            raise RuntimeError(f'Unexpected container state: {status}')
    else:
        if shutil.disk_usage(ROOT).free < 100 * 1024**3:
            raise RuntimeError('At least 100 GiB free space required for a new build')
        run('bash', 'build-rt-kernel.sh')
    code = run('docker', 'wait', name, capture=True)
    if code != '0':
        raise RuntimeError(f'Build failed with exit {code}; inspect docker logs {name}')
    if not (dest / 'SHA256SUMS').is_file():
        raise RuntimeError('Build did not produce a checksum manifest')
    return dest


def manifest_assets(paths, staging):
    staging.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f'Missing or invalid asset: {path.name}')
        if path.stat().st_size >= 2 * 1024**3:
            raise RuntimeError(f'Asset exceeds GitHub limit: {path.name}')
    manifest = staging / 'SHA256SUMS'
    manifest.write_text(''.join(f'{digest(p)}  {p.name}\n' for p in paths))
    return [*paths, manifest]


def package_assets(cfg, dest, staging):
    release, version = cfg['KERNEL_RELEASE'], cfg['PACKAGE_VERSION']
    # ディレクトリの全ファイルを公開せず、導入用の3パッケージを列挙する。
    paths = [dest / f'{kind}_{version}_amd64.deb' for kind in
             [f'linux-image-{release}', f'linux-headers-{release}', f'linux-image-{release}-dbg']]
    return manifest_assets(paths, staging)


def prepare_sources(cfg, repo):
    staging = ROOT / 'release-state' / cfg['KERNEL_RELEASE'] / 'sources'
    paths = []
    for key, hash_key in [('KERNEL_ARCHIVE', 'KERNEL_SHA256'), ('RT_PATCH_ARCHIVE', 'RT_PATCH_SHA256')]:
        path = ROOT / 'downloads' / cfg[key]
        if digest(path) != cfg[hash_key]:
            raise RuntimeError(f'Source checksum mismatch: {path.name}')
        paths.append(path)
    assets = manifest_assets(paths, staging)
    notes = staging / 'release-notes.md'
    notes.write_text(
        f"PREEMPT_RTカーネル {cfg['KERNEL_RELEASE']} の元ソースとRTパッチ。\n\n"
        f"ビルドスクリプトと設定は [ビルド時のタグ](https://github.com/{repo}/tree/"
        f"rt-{cfg['KERNEL_RELEASE']}) を参照。\n")
    return assets, notes


def prepare_assets(cfg, dest, commit, repo):
    run('sha256sum', '-c', 'SHA256SUMS', cwd=dest)
    if (dest / 'kernel.conf').read_bytes() != (ROOT / 'kernel.conf').read_bytes():
        raise RuntimeError('Artifact settings differ from current settings')
    run('docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}',
        '-e', 'HOME=/tmp', '-v', f'{ROOT}:/workspace', '-w', '/workspace',
        'rt-kernel-builder:noble', 'bash', 'scripts/check-artifacts.sh')
    staging = ROOT / 'release-state' / cfg['KERNEL_RELEASE'] / 'packages'
    assets = package_assets(cfg, dest, staging)
    notes = staging / 'release-notes.md'
    notes.write_text(
        f"Ubuntu 24.04 / amd64向けのPREEMPT_RTカーネル {cfg['KERNEL_RELEASE']}。\n\n"
        f"インストール方法は [README](https://github.com/{repo}/blob/main/README.md) を参照。\n")
    return assets, notes


def publish(repo, tag, commit, assets, notes):
    release = get_release(repo, tag)
    if release:
        ensure_target(release, commit)
        if not release['draft']:
            raise RuntimeError('Refusing to modify a published release')
    else:
        run('gh', 'release', 'create', tag, '--repo', repo, '--target', commit,
            '--draft', '--prerelease', '--title', tag, '--notes-file', str(notes))
        release = wait_for_release(repo, tag)
    remote_assets = {a['name']: a for a in release['assets']}
    expected = {p.name for p in assets}
    if set(remote_assets) - expected:
        raise RuntimeError('Draft contains unexpected assets; inspect it before retrying')
    for path in assets:
        old = remote_assets.get(path.name)
        if old and asset_matches(old, path):
            continue
        args = ['gh', 'release', 'upload', tag, str(path), '--repo', repo]
        if old:
            args.append('--clobber')  # 所有する下書きだけを再送する。
        run(*args)
    release = get_release(repo, tag)
    ensure_target(release, commit)
    if not release['draft']:
        raise RuntimeError('Release was published concurrently')
    remote_assets = {a['name']: a for a in release['assets']}
    if set(remote_assets) != expected or not all(asset_matches(remote_assets[p.name], p) for p in assets):
        raise RuntimeError('Uploaded assets failed SHA256/size verification; keeping draft')
    run('gh', 'release', 'edit', tag, '--repo', repo, '--draft=false',
        '--prerelease', '--latest=false', '--notes-file', str(notes))
    print(f'Published: https://github.com/{repo}/releases/tag/{tag}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repo):
        parser.error('Expected OWNER/REPO')
    os.chdir(ROOT)
    state = ROOT / 'release-state'
    state.mkdir(exist_ok=True)
    with (state / 'release.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if run('git', 'status', '--porcelain', capture=True):
            raise RuntimeError('Working tree must be clean')
        cfg = settings()
        commit = run('git', 'rev-parse', 'HEAD', capture=True)
        tag = 'rt-' + cfg['KERNEL_RELEASE']
        # リポジトリの認証エラーをReleaseの404と混同しない。
        run('gh', 'api', f'repos/{args.repo}', '--silent')
        release = get_release(args.repo, tag)
        if release and not release['draft']:
            print(f'Already published: {tag}; nothing to build', flush=True)
            return
        provenance = state / (cfg['KERNEL_RELEASE'] + '.commit')
        if provenance.exists():
            build_commit = provenance.read_text().strip()
            # 公開処理だけの修正では、検証済みのバイナリと元コミットを維持する。
            build_paths = ['kernel.conf', 'Dockerfile', 'build-rt-kernel.sh', 'configs',
                           'scripts/build-in-container.sh', 'scripts/kernel-settings.sh',
                           'scripts/install-kernel.sh', 'scripts/verify-kernel.sh',
                           'scripts/sample-memory.sh', 'scripts/check-artifacts.sh']
            changed = subprocess.run(['git', 'diff', '--quiet', build_commit, commit,
                                      '--', *build_paths], cwd=ROOT)
            if changed.returncode:
                raise RuntimeError('Build inputs changed; change BUILD_REVISION before retrying')
            commit = build_commit
        else:
            provenance.write_text(commit + '\n')
        dest = build(cfg)
        assets, notes = prepare_assets(cfg, dest, commit, args.repo)
        source_assets, source_notes = prepare_sources(cfg, args.repo)
        source_tag = 'sources-' + cfg['KERNEL_RELEASE']
        source_release = get_release(args.repo, source_tag)
        if source_release and not source_release['draft']:
            ensure_target(source_release, commit)
            remote = {a['name']: a for a in source_release['assets']}
            if set(remote) != {p.name for p in source_assets} or not all(
                    asset_matches(remote[p.name], p) for p in source_assets):
                raise RuntimeError('Published source assets differ from build inputs')
        else:
            publish(args.repo, source_tag, commit, source_assets, source_notes)
        publish(args.repo, tag, commit, assets, notes)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Release failed: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
