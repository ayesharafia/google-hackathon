"""Build/inspect the local wheel and install only the three new hash-pinned parsers."""
import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
work = Path(tempfile.mkdtemp(prefix='tabular-package-', dir=root/'.backend'))


def run(args):
    result = subprocess.run(args, cwd=root, text=True, capture_output=True, timeout=90, check=False)
    if result.returncode:
        raise RuntimeError('Command failed: '+repr(args)+'\n'+(result.stdout+result.stderr)[-3000:])
    return result.stdout


run(['uv', 'build', '--wheel', '--out-dir', str(work)])
wheel = next(work.glob('*.whl'))
paths = ['projects/tabular.py', 'projects/source_library.py', 'api/source_library.py',
         'resources/web/js/source-library.js', 'resources/web/js/input-editors.js',
         'resources/web/js/workbench.js', 'resources/web/css/workbench.css', 'resources/web/workbench.html']
with zipfile.ZipFile(wheel) as archive:
    for name in paths:
        source = root/('web/'+name[len('resources/web/'):] if name.startswith('resources/web/') else 'src/physimesh/'+name)
        assert archive.read('physimesh/'+name) == source.read_bytes(), name
    metadata = archive.read('physimesh_drone-0.1.0.dist-info/METADATA').decode()
    assert 'openpyxl==3.1.5' in metadata and 'defusedxml==0.7.1' in metadata
    build = json.loads(archive.read('physimesh/_build.json'))
    assert build['dependencies_sha256'] == hashlib.sha256((root/'requirements-runtime.lock').read_bytes()).hexdigest()
lock = (root/'requirements-runtime.lock').read_text().split('# Approved tabular workbook parser and XML protection.')[1]
for name in ['requirements-platform.lock', 'requirements-test.lock']:
    assert (root/name).read_text().split('# Approved tabular workbook parser and XML protection.')[1] == lock
(work/'parser.lock').write_text(lock)
run(['uv', 'venv', str(work/'venv'), '--python', '3.11'])
python = str(work/'venv/bin/python')
run(['uv', 'pip', 'install', '--python', python, '--require-hashes', '-r', str(work/'parser.lock')])
versions = run([python, '-c', ('from importlib.metadata import version; import openpyxl, defusedxml; '
                'print({p:version(p) for p in ["openpyxl","defusedxml","et-xmlfile"]})')]).strip()
print(json.dumps({'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
                  'source_assets_verified': len(paths), 'hash_verified_fresh_install': versions,
                  'limits': 'Wheel bytes/metadata and new parser install only; full image/provider integration not run.'}, indent=2))
