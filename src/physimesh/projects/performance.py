"""Retain original UTF-8 dataset bytes; hash verification precedes every use."""
import hashlib
import json
from typing import Literal

from pydantic import model_validator

from physimesh.core.artifacts import ArtifactStore
from physimesh.drone.performance import RotorMapV1
from physimesh.projects.contracts import Digest, Record, _constant, _pairs


def performance_refs(snapshot: dict) -> set[str]:
    refs = {r['map_ref'] for r in snapshot['rotors'] if isinstance(r.get('map_ref'), str)}
    for case in snapshot['mission'].get('cases', []):
        overrides = case.get('performance_source_by_rotor') if isinstance(case, dict) else None
        if isinstance(overrides, dict):
            refs.update(value for value in overrides.values() if isinstance(value, str))
    scenarios = snapshot['fidelity'].get('local_pilot', {}).get('scenarios', [])
    if isinstance(scenarios, list):
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                continue
            groups = [scenario.get('map_sources_by_rotor', {})]
            by_case = scenario.get('map_sources_by_case', {})
            if isinstance(by_case, dict):
                groups.extend(by_case.values())
            for group in groups:
                if isinstance(group, dict):
                    refs.update(value for value in group.values() if isinstance(value, str))
    return refs


class ConditionedSourceV1(Record):
    schema_version: Literal['rotor_map_conditioned_v1']
    raw_source_sha256: Digest
    profile: dict

    @model_validator(mode='after')
    def profile_version(self):
        if self.profile.get('schema_version') != 'conditioned_rotor_profile_v1':
            raise ValueError('unsupported conditioned profile version')
        return self


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


def source_bytes(store: ArtifactStore, digest: str) -> bytes:
    with store.open(digest) as stream:
        raw = stream.read(500_001)
    if len(raw) > 500_000 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('rotor-map source byte integrity failed')
    return raw


def retain_conditioned_map(store: ArtifactStore, digest: str, policy) -> dict:
    from physimesh.drone.conditioning import condition_map
    from physimesh.drone.provenance import canonical_json
    model = parse_map(source_bytes(store, digest))
    profile = condition_map(model, policy)
    record = ConditionedSourceV1(schema_version='rotor_map_conditioned_v1', raw_source_sha256=digest,
                                profile=profile)
    raw = canonical_json(record.model_dump(mode='json')).encode()
    conditioned = store.put_bytes(raw, kind='rotor_map_conditioned_v1', meta={'raw_source_sha256': digest})
    return {'source_sha256': conditioned, 'raw_source_sha256': digest,
            'dataset': model.model_dump(mode='json'), 'conditioning': profile}


def load_map(store: ArtifactStore, digest: str):
    from physimesh.drone.conditioning import ConditionedMap, validate_retained_profile
    from physimesh.drone.provenance import canonical_json
    raw = source_bytes(store, digest)
    data = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if data.get('schema_version') != 'rotor_map_conditioned_v1':
        return parse_map(raw)
    record = ConditionedSourceV1.model_validate_json(canonical_json(data))
    original = parse_map(source_bytes(store, record.raw_source_sha256))
    profile = validate_retained_profile(original, record.profile)
    return ConditionedMap(original, record.raw_source_sha256, digest, profile)
