"""Verify packaged AI assets and optional dependency metadata."""
import glob
import hashlib
import json
import zipfile
from pathlib import Path

wheel = Path(glob.glob('.backend/agent-wheel/*.whl')[0])
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
    manifest = json.loads(archive.read('physimesh/_build.json'))
    for path in ('agent/mcp.py', 'agent/service.py', 'resources/web/js/agent-workspace.js',
                 'resources/web/css/workbench.css', 'resources/web/workbench.html'):
        data = archive.read('physimesh/' + path)
        assert hashlib.sha256(data).hexdigest() == manifest['resources'][path], path
    lock = archive.read('physimesh/resources/locks/requirements-mcp.lock')
    assert lock == Path('requirements-mcp.lock').read_bytes()
    assert hashlib.sha256(lock).hexdigest() == manifest['optional_dependencies_sha256']['mcp']
    metadata = archive.read(next(n for n in names if n.endswith('.dist-info/METADATA'))).decode()
    assert 'mcp==2.3.0; extra == "mcp"' in metadata
print('Wheel AI modules, web assets, optional lock and metadata verified.')
