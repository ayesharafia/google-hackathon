"""Read-only interpretation of retained study bytes, never a new capacity calculation.

Callers must verify the retained study and frozen revision before exposing this
projection. Original result formats and approval/qualification remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

SUMMARY_VERSION = 'study_summary_v1'
SUMMARY_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _payload(status: str, value):
    if status not in ('feasible', 'supported') or value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('retained summary payload must be finite and nonnegative')
    return value


def summarize_study(raw: bytes) -> dict:
    """Project recorded values without solving, rounding or combining their scopes."""
    record = json.loads(raw)
    spec = record['specification']
    historical = record['schema_version'] not in ('local_mission_capacity_v3', 'local_mission_capacity_v4')
    scenario = record.get('scenario_analysis') or {}
    allowable = record.get('external_allowables') or {}
    scenario_status = scenario.get('status', 'not_declared')
    allowable_status = allowable.get('status', 'not_declared')
    nominal_qualification = record.get('qualification', 'Historical qualification was not recorded.')
    bounds = {
        'nominal': {
            'label': 'Reported historical model bound' if historical else 'Nominal model payload lower bound',
            'status': record['outcome'],
            'payload_kg': _payload(record['outcome'], record.get('payload_lower_bound_kg')),
            'qualification': nominal_qualification,
        },
        'scenario': {
            'label': 'Scenario-supported payload',
            'status': scenario_status,
            'payload_kg': _payload(scenario_status, scenario.get('supported_payload_kg')),
            'limiting_ids': list(scenario.get('limiting_scenario_ids', [])),
            'qualification': scenario.get('qualification', 'No deterministic scenario envelope was declared.'),
        },
        'allowable': {
            'label': 'Checked allowable payload',
            'status': allowable_status,
            'payload_kg': _payload(allowable_status, allowable.get('feasible_capped_payload_kg')),
            'declared_cap_kg': allowable.get('declared_approved_cap_kg'),
            'limiting_ids': list(allowable.get('limiting_cap_ids', [])),
            'approval_authentication': 'not_authenticated',
            'qualification': 'External cap approval is a caller declaration, not authenticated engineering acceptance. '
                             + allowable.get('qualification', 'No external allowable was declared.'),
        },
    }
    return {
        'schema_version': SUMMARY_VERSION,
        'study_sha256': record['study_sha256'],
        'study_json_sha256': hashlib.sha256(raw).hexdigest(),
        'project_id': spec['project_id'],
        'revision_sha256': spec['revision_sha256'],
        'snapshot_sha256': spec['snapshot_sha256'],
        'result_schema_version': record['schema_version'],
        'model_version': spec.get('model', {}).get('model_version', record.get('model_version', 'not_recorded')),
        'outcome': record['outcome'],
        'data_scope': record.get('data_scope', 'not_recorded'),
        'engineering_approval': record.get('engineering_approval', spec.get('engineering_approval', 'not_recorded')),
        'qualification': nominal_qualification,
        'historical': historical,
        'bounds': bounds,
        'cases': [
            {'case_id': case['case_id'], 'required': case.get('required'), 'outcome': case['outcome'],
             'payload_kg': _payload(case['outcome'], (case.get('candidate') or {}).get('payload_kg')),
             'active_constraints': list(case.get('active_constraints', []))}
            for case in record.get('cases', [])
        ],
        'scenarios': [
            {'scenario_id': item['scenario_id'], 'outcome': item['result']['outcome'],
             'payload_kg': _payload(item['result']['outcome'], item['result'].get('payload_lower_bound_kg')),
             'source_note': item.get('source_note', ''), 'correlation_note': item.get('correlation_note', '')}
            for item in scenario.get('scenarios', [])
        ],
        'performance_source_sha256': list(spec.get('performance_source_sha256', [])),
    }
