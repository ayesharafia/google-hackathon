"""Reproduce retained synthetic V4 evidence using source bytes; refuses a changed model.

This does not validate an aircraft or claim byte-deterministic optimizer commands.
"""
import hashlib
import json
import math
import tempfile
from pathlib import Path

from physimesh.core.artifacts import ArtifactStore
from physimesh.drone.capacity import capacity_from_snapshot
from physimesh.drone.snapshot_hash import snapshot_sha256
from physimesh.projects.contracts import parse_snapshot
from physimesh.projects.performance import load_map
from physimesh.projects.studies import model_identity

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'docs/demo/assets'
record = json.loads((ASSETS/'synthetic-conditioned-study.json').read_bytes())
snapshot = parse_snapshot((ASSETS/'synthetic-conditioned-snapshot.json').read_text())
assert snapshot_sha256(snapshot) == record['specification']['snapshot_sha256']
identity = {**model_identity(), 'model_version': record['model_version']}
assert identity == record['specification']['model'], 'Changed model/library identity; reproduce with retained source versions first'
with tempfile.TemporaryDirectory(prefix='physicore-reproduction-') as root:
    store = ArtifactStore(Path(root))
    for path in (ASSETS/'model-sources').glob('*.json'):
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == path.stem
        assert store.put_bytes(raw, kind='retained_fixture', meta={}) == path.stem
    sources = {digest: load_map(store, digest) for digest in record['specification']['performance_source_sha256']}
    result = capacity_from_snapshot(snapshot, sources)
    assert result['schema_version'] == record['schema_version']
    assert result['outcome'] == record['outcome'] == 'feasible'
    assert result['limiting_case_id'] == record['limiting_case_id']
    assert math.isclose(result['payload_lower_bound_kg'], record['payload_lower_bound_kg'], rel_tol=1e-9, abs_tol=1e-9)
    for before, after in zip(record['cases'], result['cases'], strict=True):
        assert before['case_id'] == after['case_id']
        assert math.isclose(before['candidate']['payload_kg'], after['candidate']['payload_kg'], rel_tol=1e-9, abs_tol=1e-9)
    print(json.dumps({'scope':'analytic_fixture', 'outcome':result['outcome'], 'payload_lower_bound_kg':result['payload_lower_bound_kg'], 'limiting_case_id':result['limiting_case_id'], 'qualification':'Software/model reproduction only; engineering approval pending'}, indent=2))
