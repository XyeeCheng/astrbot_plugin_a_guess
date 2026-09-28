import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from install_ubuntu import NAME, check_target, install, verify

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = self.base / 'release'
        self.source.mkdir()
        paths = ['main.py', 'metadata.yaml', 'questions.json', '_conf_schema.json',
                 'aguess/core.py', 'aguess/matcher.py', 'aguess/version.py', 'install_ubuntu.py']
        for name in paths:
            dest = self.source / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / name).read_bytes())
        self.files = {n: hashlib.sha256((self.source / n).read_bytes()).hexdigest() for n in paths}
        self.manifest()
        self.target = self.base / 'phoebe' / 'data' / 'plugins' / NAME
        self.target.parent.mkdir(parents=True)
        self.runtime = self.target.parent.parent / 'plugin_data' / NAME
        self.runtime.mkdir(parents=True)
        (self.runtime / 'a_guess.sqlite3').write_bytes(b'untouched-game-database')
        self.other = self.target.parent / 'another_plugin'
        self.other.mkdir()
        (self.other / 'keep').write_text('unchanged')

    def manifest(self):
        (self.source / 'package-manifest.json').write_text(json.dumps({
            'format': 1, 'plugin': NAME, 'version': '1.2.0', 'files': self.files}), encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_and_new_install_only_copy_verified_files(self):
        (self.source / 'unlisted.txt').write_text('not shipped')
        self.assertEqual(verify(self.source)['version'], '1.2.0')
        result = install(self.source, self.target, True)
        self.assertIsNone(result['backup'])
        self.assertFalse((self.target / 'unlisted.txt').exists())
        self.assertEqual(verify(self.target)['files'], self.files)
        self.assertEqual((self.runtime / 'a_guess.sqlite3').read_bytes(), b'untouched-game-database')
        self.assertEqual((self.other / 'keep').read_text(), 'unchanged')

    def test_update_keeps_old_sources_outside_plugin_scan(self):
        self.target.mkdir()
        (self.target / 'metadata.yaml').write_text(f'name: {NAME}\nversion: v1.1.1\n')
        (self.target / 'old.py').write_text('OLD = True\n')
        result = install(self.source, self.target, True)
        backup = Path(result['backup'])
        self.assertEqual((backup / 'old.py').read_text(), 'OLD = True\n')
        self.assertNotIn(self.target.parent, backup.parents)
        self.assertFalse((self.target / 'old.py').exists())
        self.assertEqual((self.runtime / 'a_guess.sqlite3').read_bytes(), b'untouched-game-database')

    def test_failed_final_rename_restores_previous_sources(self):
        self.target.mkdir()
        (self.target / 'metadata.yaml').write_text(f'name: {NAME}\n')
        (self.target / 'old.py').write_text('previous version')
        original = Path.rename
        def fail_stage(path, dest):
            if path.name.startswith('.a-guess-stage-'):
                raise OSError('injected rename failure')
            return original(path, dest)
        with patch.object(Path, 'rename', fail_stage):
            with self.assertRaisesRegex(OSError, 'injected'):
                install(self.source, self.target, True)
        self.assertEqual((self.target / 'old.py').read_text(), 'previous version')
        self.assertFalse(list(self.runtime.rglob('.a-guess-stage-*')))

    def test_refuses_without_disabled_plugin_acknowledgement(self):
        with self.assertRaisesRegex(ValueError, 'Disable this plugin'):
            install(self.source, self.target)
        self.assertFalse(self.target.exists())

    def test_changed_payload_does_not_modify_existing_target(self):
        (self.source / 'main.py').write_text('changed = True\n')
        with self.assertRaisesRegex(ValueError, 'changed package file'):
            install(self.source, self.target, True)
        self.assertFalse(self.target.exists())

    def test_rejects_traversal_and_runtime_files(self):
        for name in ('../escape', '/tmp/escape', 'data/secret', '.git/config', '.env', 'a/../b', 'a\\b'):
            self.files[name] = 'fake'
            self.manifest()
            with self.assertRaisesRegex(ValueError, 'Unsafe payload'):
                verify(self.source)
            del self.files[name]

    def test_target_and_source_cannot_overlap(self):
        for target in (self.source, self.source / 'plugins' / NAME, self.base / NAME, self.other):
            with self.assertRaises(ValueError):
                check_target(self.source, target)

    def test_unrelated_existing_directory_is_preserved(self):
        self.target.mkdir()
        (self.target / 'metadata.yaml').write_text('name: another_plugin\n')
        with self.assertRaisesRegex(ValueError, 'not this plugin'):
            install(self.source, self.target, True)
        self.assertEqual((self.target / 'metadata.yaml').read_text(), 'name: another_plugin\n')

    def test_symlink_source_target_and_backup_parent_rejected(self):
        linked = self.base / 'linked-source'
        try:
            linked.symlink_to(self.source, target_is_directory=True)
        except OSError:
            self.skipTest('OS cannot create symlinks in this environment')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            install(linked, self.target, True)
        self.target.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            install(self.source, self.target, True)
        self.target.unlink()
        backup_root = self.runtime / 'code_backups'
        backup_root.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            install(self.source, self.target, True)


if __name__ == '__main__':
    unittest.main()
