#!/usr/bin/env python3
"""Offline source installer. Run from the verified GitHub release archive."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone

NAME = 'astrbot_plugin_a_guess'
ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def no_symlinks(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f'Symlink paths are not accepted: {part}')


def verify(source):
    source = Path(source).absolute()
    no_symlinks(source)
    manifest_path = source / 'package-manifest.json'
    no_symlinks(manifest_path)
    if not manifest_path.is_file():
        raise ValueError('Missing package-manifest.json; use the release ZIP or Ubuntu tar.gz.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('format') != 1 or manifest.get('plugin') != NAME:
        raise ValueError('Unexpected manifest identity or format')
    files = manifest.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('Empty package manifest')
    required = {'main.py', 'metadata.yaml', 'questions.json', '_conf_schema.json',
                'aguess/core.py', 'aguess/matcher.py', 'aguess/version.py', 'install_ubuntu.py'}
    if not required <= files.keys():
        raise ValueError('Incomplete plugin payload')
    for name, expected in files.items():
        rel = PurePosixPath(name)
        if (not isinstance(name, str) or rel.is_absolute() or '..' in rel.parts
                or '\\' in name or ':' in name or rel.as_posix() != name
                or name == 'package-manifest.json' or not rel.parts
                or rel.parts[0] in ('data', '.git', 'dist')
                or any(p.startswith('.env') or p.endswith(('.sqlite3', '.db')) for p in rel.parts)):
            raise ValueError(f'Unsafe payload path: {name}')
        path = source.joinpath(*rel.parts)
        no_symlinks(path)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f'Missing or changed package file: {name}')
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8'), filename=name)
    if f'name: {NAME}' not in (source / 'metadata.yaml').read_text(encoding='utf-8').splitlines():
        raise ValueError('Plugin metadata identity mismatch')
    bank = json.loads((source / 'questions.json').read_text(encoding='utf-8'))
    if len(bank.get('questions', [])) != 200:
        raise ValueError('Expected the 200-card edition')
    return manifest


def check_target(source, target):
    source, target = Path(source).absolute(), Path(target).absolute()
    no_symlinks(source)
    no_symlinks(target)
    source, target = source.resolve(), target.resolve()
    if target.name != NAME or target.parent.name != 'plugins':
        raise ValueError(f'Target must be an AstrBot plugins/{NAME} directory')
    if source == target or source in target.parents or target in source.parents:
        raise ValueError('Source and target must be separate directories')
    if not target.parent.is_dir():
        raise ValueError('The selected AstrBot plugins directory does not exist')
    if target.exists():
        if not target.is_dir():
            raise ValueError('Target is not a directory')
        metadata = target / 'metadata.yaml'
        if not metadata.is_file() or f'name: {NAME}' not in metadata.read_text(encoding='utf-8').splitlines():
            raise ValueError('Existing target is not this plugin')
        # Refuse linked files before moving the whole old source into a backup.
        for path in target.rglob('*'):
            no_symlinks(path)
    return target


def install(source, target, plugin_stopped=False):
    if not plugin_stopped:
        raise ValueError('Disable this plugin in AstrBot first, then pass --plugin-stopped.')
    source = Path(source).absolute()
    manifest = verify(source)
    target = check_target(source, target)
    # Backups live outside plugins/, so AstrBot cannot load them as extra plugins.
    backup_root = target.parent.parent / 'plugin_data' / NAME / 'code_backups'
    no_symlinks(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    # Use the same filesystem as the target for atomic directory renames.
    stage = Path(tempfile.mkdtemp(prefix='.a-guess-stage-', dir=backup_root))
    backup = backup_root / stamp
    owner = target.stat() if target.exists() else target.parent.stat()
    moved = False
    try:
        for name in [*manifest['files'], 'package-manifest.json']:
            dest = stage / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, dest)
        verify(stage)
        # sudo must not make the next AstrBot update fail with root-owned sources.
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            for path in [*stage.rglob('*'), stage, backup_root, backup_root.parent]:
                os.chown(path, owner.st_uid, owner.st_gid)
        if target.exists():
            target.rename(backup)
            moved = True
        try:
            stage.rename(target)
        except BaseException:
            if moved:
                backup.rename(target)
                moved = False
            raise
    finally:
        if stage.exists():
            # stage is a freshly created directory under the verified backup root.
            if stage.resolve().parent != backup_root.resolve():
                raise ValueError('Unexpected staging path; refusing cleanup')
            shutil.rmtree(stage)
    return {'version': manifest['version'], 'target': str(target),
            'backup': str(backup) if moved else None,
            'next': 'Enable or reload this plugin in the Phoebe AstrBot dashboard.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'install'))
    parser.add_argument('--target', type=Path, default=Path('/opt/phoebe/data/plugins') / NAME)
    parser.add_argument('--plugin-stopped', action='store_true', help='Confirm this plugin has been disabled in AstrBot')
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Run this installer on Ubuntu/Linux; use the AstrBot dashboard on Windows.')
    try:
        if args.action == 'check':
            manifest = verify(ROOT)
            print(f"OK: {NAME} v{manifest['version']}, {len(manifest['files'])} verified source files, 200 cards")
        else:
            print(json.dumps(install(ROOT, args.target, args.plugin_stopped), ensure_ascii=False, indent=2))
    except (OSError, ValueError, SyntaxError, KeyError) as error:
        parser.exit(1, f'Installation stopped: {error}\n')


if __name__ == '__main__':
    main()
