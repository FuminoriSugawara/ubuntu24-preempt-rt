"""Releaseの公開条件と共通設定の回帰試験。ネットワークや実際のDockerは使わない。"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('release', ROOT / 'scripts/release-kernel.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.asset = self.root / 'kernel.deb'
        self.asset.write_bytes(b'example package')
        self.notes = self.root / 'notes.md'
        self.notes.write_text('release notes')
        self.remote = {'name': self.asset.name, 'size': self.asset.stat().st_size,
                       'state': 'uploaded', 'digest': 'sha256:' + release.digest(self.asset)}

    def draft(self, assets=()):
        return {'draft': True, 'target_commitish': 'abc', 'assets': list(assets)}

    def test_unpublished_tag_lookup_finds_draft(self):
        response = subprocess.CompletedProcess([], 1, '', 'gh: Not Found (HTTP 404)')
        draft = dict(self.draft(), tag_name='tag')
        with patch.object(release.subprocess, 'run', return_value=response), patch.object(release, 'run', return_value=json.dumps([[draft]])):
            self.assertEqual(release.get_release('owner/repo', 'tag'), draft)

    def test_absent_release_returns_none(self):
        response = subprocess.CompletedProcess([], 1, '', 'gh: Not Found (HTTP 404)')
        with patch.object(release.subprocess, 'run', return_value=response), patch.object(release, 'run', return_value='[[]]'):
            self.assertIsNone(release.get_release('owner/repo', 'tag'))

    def test_auth_failure_is_not_missing_release(self):
        response = subprocess.CompletedProcess([], 1, '', 'gh: Forbidden (HTTP 403)')
        with patch.object(release.subprocess, 'run', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'lookup failed'):
                release.get_release('owner/repo', 'tag')

    def test_waits_for_new_draft_to_appear(self):
        draft = self.draft()
        with patch.object(release, 'get_release', side_effect=[None, None, draft]), patch.object(release.time, 'sleep') as sleep:
            self.assertEqual(release.wait_for_release('owner/repo', 'tag'), draft)
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])

    def test_missing_draft_stops_after_bounded_retries(self):
        with patch.object(release, 'get_release', return_value=None), patch.object(release.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'retry to resume'):
                release.wait_for_release('owner/repo', 'tag')

    def test_upload_then_publish(self):
        with patch.object(release, 'get_release', side_effect=[None, self.draft(), self.draft([self.remote])]), patch.object(release, 'run') as run:
            release.publish('owner/repo', 'tag', 'abc', [self.asset], self.notes)
        commands = [call.args for call in run.call_args_list]
        self.assertEqual([args[2] for args in commands], ['create', 'upload', 'edit'])
        self.assertIn('--draft', commands[0])
        self.assertIn('--draft=false', commands[-1])
        self.assertIn('--prerelease', commands[-1])

    def test_resume_verified_upload(self):
        with patch.object(release, 'get_release', return_value=self.draft([self.remote])), patch.object(release, 'run') as run:
            release.publish('owner/repo', 'tag', 'abc', [self.asset], self.notes)
        self.assertEqual([c.args[2] for c in run.call_args_list], ['edit'])

    def test_corrupt_upload_stays_draft(self):
        corrupt = dict(self.remote, digest='sha256:' + '0' * 64)
        with patch.object(release, 'get_release', side_effect=[self.draft(), self.draft([corrupt])]), patch.object(release, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'SHA256'):
                release.publish('owner/repo', 'tag', 'abc', [self.asset], self.notes)
        self.assertNotIn('edit', [c.args[2] for c in run.call_args_list])

    def test_existing_release_cannot_be_overwritten(self):
        for remote in [dict(self.draft(), draft=False), dict(self.draft(), target_commitish='other')]:
            with self.subTest(remote=remote), patch.object(release, 'get_release', return_value=remote), patch.object(release, 'run') as run:
                with self.assertRaises(RuntimeError):
                    release.publish('owner/repo', 'tag', 'abc', [self.asset], self.notes)
                run.assert_not_called()

    def test_extra_asset_blocks_publication(self):
        extra = dict(self.remote, name='unexpected.log')
        with patch.object(release, 'get_release', return_value=self.draft([extra])), patch.object(release, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'unexpected'):
                release.publish('owner/repo', 'tag', 'abc', [self.asset], self.notes)
            run.assert_not_called()

    def test_build_failure_stops_pipeline(self):
        cfg = {'KERNEL_RELEASE': 'test', 'DEFAULT_CONTAINER_NAME': 'builder'}
        with patch.object(release, 'ROOT', self.root), patch.object(release, 'run', side_effect=['builder', str(self.root), 'running', '137']):
            with self.assertRaisesRegex(RuntimeError, 'exit 137'):
                release.build(cfg)

    def test_foreign_container_is_not_started(self):
        cfg = {'KERNEL_RELEASE': 'test', 'DEFAULT_CONTAINER_NAME': 'builder'}
        with patch.object(release, 'ROOT', self.root), patch.object(release, 'run', side_effect=['builder', '/another/checkout']) as run:
            with self.assertRaisesRegex(RuntimeError, 'another checkout'):
                release.build(cfg)
            self.assertFalse(any('start' in call.args for call in run.call_args_list))

    def test_package_assets_exclude_docs_sources_and_old_manifest(self):
        cfg = {'KERNEL_RELEASE': '6.17.5-rt7', 'PACKAGE_VERSION': '6.17.5-rt7-1'}
        names = [f'{kind}_6.17.5-rt7-1_amd64.deb' for kind in
                 ['linux-image-6.17.5-rt7', 'linux-headers-6.17.5-rt7', 'linux-image-6.17.5-rt7-dbg']]
        for name in names:
            (self.root / name).write_bytes(name.encode())
        (self.root / 'README.md').write_text('private extra')
        (self.root / 'SHA256SUMS').write_text('original manifest')
        assets = release.package_assets(cfg, self.root, self.root / 'stage')
        self.assertEqual({p.name for p in assets}, {*names, 'SHA256SUMS'})
        self.assertEqual((self.root / 'SHA256SUMS').read_text(), 'original manifest')
        self.assertEqual(len(assets[-1].read_text().splitlines()), 3)
        (self.root / names[0]).unlink()
        with self.assertRaisesRegex(RuntimeError, 'Missing'):
            release.package_assets(cfg, self.root, self.root / 'stage')

    def test_snapshot_and_revision_sort(self):
        repo = self.root / 'repo'
        (repo / 'scripts').mkdir(parents=True)
        shutil.copy2(ROOT / 'scripts/kernel-settings.sh', repo / 'scripts/kernel-settings.sh')
        original = (ROOT / 'kernel.conf').read_text()
        (repo / 'kernel.conf').write_text(original.replace('BUILD_REVISION=1', 'BUILD_REVISION=10'))
        def read(path):
            return subprocess.check_output(['bash', '-euc', 'source "$1"; printf "%s %s" "$KERNEL_RELEASE" "$PACKAGE_VERSION"', 'test', str(path)], text=True)
        self.assertEqual(read(repo / 'scripts/kernel-settings.sh'), '6.17.5-rt7-build10 6.17.5-rt7-10')
        artifact = self.root / 'artifact'
        artifact.mkdir()
        shutil.copy2(ROOT / 'kernel.conf', artifact / 'kernel.conf')
        shutil.copy2(ROOT / 'scripts/kernel-settings.sh', artifact / 'kernel-settings.sh')
        self.assertEqual(read(artifact / 'kernel-settings.sh'), '6.17.5-rt7 6.17.5-rt7-1')
        subprocess.run(['dpkg', '--validate-version', '6.17.5-rt7-2'], check=True)
        subprocess.run(['dpkg', '--compare-versions', '6.17.5-rt7-10', 'gt', '6.17.5-rt7-2'], check=True)


if __name__ == '__main__':
    unittest.main()
