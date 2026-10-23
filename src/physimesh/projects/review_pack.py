"""Bounded handoff of verified retained bytes; no solver or source conversion."""
from __future__ import annotations

import hashlib
import io
import json
import re
import threading
import zipfile

from physimesh.drone.conditioning import ConditionedMap
from physimesh.drone.provenance import canonical_json
from physimesh.drone.snapshot_hash import snapshot_sha256

from .performance import load_map, performance_refs, source_bytes
from .reports import report_identity

MAX_MEMBERS = 128
MAX_BYTES = 40 * 1024 * 1024
BUILD_SLOTS = threading.BoundedSemaphore(2)
EXCLUSIONS = [
    'CAD/STL geometry assets', 'Original CSV/XLSX files and conversion manifests',
    'Authenticated engineering signatures or operational approval',
    'Solver source, executable software, containers and runtime dependencies',
]
README = """PhysiCore Study Review Pack v1

Start with report.pdf; study.json is the authoritative retained result.
snapshot.json is the frozen input, never the current mutable draft.
report-receipt.json binds the PDF to retained input/result and renderer identities.
sources/<SHA-256>.json holds exact retained rotor-source bytes. Conditioned
sources include their referenced raw rotor-map JSON as a separate member.
manifest.json identifies bindings, source dependencies, scope and exclusions.
Its snapshot_sha256 uses si_numeric_snapshot_v1 (the study binding);
snapshot_json_sha256 and hashes.json identify exact snapshot file bytes.
The PDF receipt keeps its existing snapshot_sha256 byte-hash convention.
hashes.json lists every other member's SHA-256 and byte count. Verify these
against the extracted bytes. The ZIP response also provides a whole-file checksum.
Checksums establish byte consistency, not authenticity or scientific correctness.

EXCLUSIONS
CAD/STL assets; original CSV/XLSX files and conversion manifests; authenticated
engineering signatures; solver source/build/container/runtime dependencies.
Raw rotor-map JSON is not the original measurement spreadsheet. No unique
original import association is inferred. This is not a complete project backup
or a standalone solver replay. Models and real-aircraft inputs remain subject
to their recorded limitations and qualified review. No flight approval is granted.
"""


class PackBusy(Exception):
    pass


def build_review_pack(studies, project_id: str, study: str, pdf_record: tuple) -> tuple[bytes, dict]:
    if not BUILD_SLOTS.acquire(blocking=False):
        raise PackBusy('Review pack capacity is busy. Try again shortly.')
    try:
        return _build(studies, project_id, study, pdf_record)
    finally:
        BUILD_SLOTS.release()


def _build(studies, project_id, study, pdf_record):
    raw, snapshot_raw = studies.report_inputs(project_id, study)
    record, snapshot = json.loads(raw), json.loads(snapshot_raw)
    spec = record['specification']
    if snapshot_sha256(snapshot) != spec['snapshot_sha256']:
        raise ValueError('Review pack frozen snapshot identity differs from the study.')
    pdf, receipt = pdf_record
    pdf_hash = hashlib.sha256(pdf).hexdigest()
    if receipt != {**report_identity(raw, snapshot_raw), 'pdf_sha256': pdf_hash} or not pdf.startswith(b'%PDF-'):
        raise ValueError('Review pack PDF receipt does not match the retained study.')
    refs = performance_refs(snapshot)
    recorded = spec.get('performance_source_sha256')
    if (not isinstance(recorded, list) or any(not isinstance(d, str) or not re.fullmatch('[0-9a-f]{64}', d) for d in recorded)
            or len(recorded) != len(set(recorded)) or refs != set(recorded)):
        raise ValueError('Review pack rotor-source bindings differ from frozen inputs.')
    if len(refs) > MAX_MEMBERS - 7:
        raise ValueError('Review pack exceeds the 128-member limit.')
    files, total = {}, 0

    def add(name, content):
        nonlocal total
        if name in files:
            if files[name] != content:
                raise ValueError('Conflicting review pack member.')
            return
        if len(files) >= MAX_MEMBERS or total + len(content) > MAX_BYTES:
            raise ValueError('Review pack exceeds the 128-member or 40 MiB uncompressed limit.')
        files[name] = content
        total += len(content)

    add('study.json', raw)
    add('snapshot.json', snapshot_raw.encode('utf-8'))
    add('report.pdf', pdf)
    add('report-receipt.json', canonical_json(receipt).encode('utf-8'))
    add('README.txt', README.encode('utf-8'))
    dependencies = []
    for digest in sorted(refs):
        try:
            model = load_map(studies.projects.artifacts, digest)
            add('sources/' + digest + '.json', source_bytes(studies.projects.artifacts, digest))
            raw_ref = model.source_sha256 if isinstance(model, ConditionedMap) else None
            if raw_ref:
                add('sources/' + raw_ref + '.json', source_bytes(studies.projects.artifacts, raw_ref))
        except (KeyError, OSError) as exc:
            raise ValueError('A required retained rotor source is unavailable.') from exc
        dependencies.append({'source_sha256': digest, 'raw_source_sha256': raw_ref})
    manifest = {
        'schema_version': 'study_review_pack_v1', 'project_id': project_id, 'study_sha256': study,
        'revision_sha256': spec['revision_sha256'], 'snapshot_sha256': spec['snapshot_sha256'],
        'snapshot_hash_scheme': 'si_numeric_snapshot_v1',
        'snapshot_json_sha256': hashlib.sha256(snapshot_raw.encode('utf-8')).hexdigest(),
        'study_json_sha256': hashlib.sha256(raw).hexdigest(), 'pdf_sha256': pdf_hash,
        'model': spec.get('model'), 'outcome': record.get('outcome'),
        'data_scope': record.get('data_scope', 'not_recorded'),
        'engineering_approval': record.get('engineering_approval', spec.get('engineering_approval', 'not_recorded')),
        'qualification': record.get('qualification', 'Historical qualification not recorded.'),
        'source_dependencies': dependencies, 'exclusions': EXCLUSIONS,
        'limits': {'max_members': MAX_MEMBERS, 'max_uncompressed_bytes': MAX_BYTES},
        'checksum_scope': 'Byte consistency only; not an authenticated signature or physical acceptance.',
    }
    add('manifest.json', canonical_json(manifest).encode('utf-8'))
    hashes = {name: {'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
              for name, content in sorted(files.items())}
    add('hashes.json', canonical_json(hashes).encode('utf-8'))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return stream.getvalue(), manifest
