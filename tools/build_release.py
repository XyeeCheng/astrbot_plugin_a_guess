"""Build a release from a clean, committed checkout; no runtime data is included."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build():
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    if dirty.strip():
        raise SystemExit('Commit the reviewed changes before building a release.')
    archive = subprocess.check_output(['git', 'archive', '--format=zip', 'HEAD'], cwd=ROOT)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / 'astrbot_plugin_a_guess'
        source.mkdir()
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            z.extractall(source)
        version_ns = {}
        exec((source / 'aguess/version.py').read_text(encoding='utf-8'), version_ns)
        version = version_ns['PLUGIN_VERSION']
        files = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(source.rglob('*')) if p.is_file()}
        for name in files:
            parts = Path(name).parts
            if parts[0] in ('data', 'dist', '.git') or name.endswith(('.sqlite3', '.db')) or '.env' in parts:
                raise SystemExit(f'Unexpected runtime file in archive: {name}')
        manifest = {'format': 1, 'plugin': 'astrbot_plugin_a_guess', 'version': version,
                    'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    'files': files}
        (source / 'package-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        dest = ROOT / 'dist'
        dest.mkdir(exist_ok=True)
        zip_path = dest / f'astrbot_plugin_a_guess-v{version}.zip'
        tar_path = dest / f'astrbot_plugin_a_guess-v{version}-ubuntu.tar.gz'
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(source.rglob('*')):
                if p.is_file():
                    z.write(p, (Path(source.name) / p.relative_to(source)).as_posix())
        with tarfile.open(tar_path, 'w:gz', format=tarfile.PAX_FORMAT) as tar:
            for p in sorted(source.rglob('*')):
                if p.is_file():
                    info = tar.gettarinfo(str(p), (Path(source.name) / p.relative_to(source)).as_posix())
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ''
                    info.mode = 0o644
                    with p.open('rb') as f:
                        tar.addfile(info, f)
        sums = dest / f'SHA256SUMS-v{version}.txt'
        sums.write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in (zip_path, tar_path)), encoding='ascii', newline='\n')
        print(sums.read_text())


if __name__ == '__main__':
    build()
