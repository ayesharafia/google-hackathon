"""Read/verify packaged application identity without changing numerical model identity."""
import hashlib
import json
from pathlib import Path


def build_identity(*, verify=False):
    package = Path(__file__).parents[1]
    manifest = package/'_build.json'
    if not manifest.exists():
        return {'schema_version': 'application_build_v1', 'build_sha256': None,
                'qualification': 'Editable source checkout; no immutable packaged build identity.'}
    record = json.loads(manifest.read_text())
    declared = record.pop('build_sha256')
    raw = json.dumps(record, sort_keys=True, separators=(',', ':')).encode()
    if hashlib.sha256(raw).hexdigest() != declared:
        raise ValueError('packaged build identity integrity failed')
    if verify:
        for name, digest in record['resources'].items():
            path = (package/name).resolve()
            if not path.is_relative_to(package.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('packaged resource integrity failed: '+name)
    return {**record, 'build_sha256': declared}
