"""Retain original UTF-8 dataset bytes; hash verification precedes every use."""
import hashlib

from physimesh.core.artifacts import ArtifactStore
from physimesh.drone.performance import RotorMapV1
from physimesh.projects.contracts import _constant, _pairs


def parse_map(raw: bytes) -> RotorMapV1:
    import json
    data = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    # JSON-mode parsing supports tuple wire arrays while keeping strict primitive types.
    from physimesh.drone.provenance import canonical_json
    return RotorMapV1.model_validate_json(canonical_json(data))


def retain_map(store: ArtifactStore, raw: bytes) -> dict:
    if len(raw) > 500_000:
        raise ValueError('rotor-map input exceeds 500000 bytes')
    model = parse_map(raw)
    digest = store.put_bytes(raw, kind='rotor_map_v1', meta={'source_kind': model.source_kind})
    return {'source_sha256': digest, 'dataset': model.model_dump(mode='json'),
            'qualification': 'Retained source declaration; physical coverage and accuracy are not validated.'}


def load_map(store: ArtifactStore, digest: str) -> RotorMapV1:
    with store.open(digest) as stream:
        raw = stream.read(500_001)
    if len(raw) > 500_000 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('rotor-map source byte integrity failed')
    return parse_map(raw)
