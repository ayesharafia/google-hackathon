"""Local, declaration-only aircraft intake inventory; never engineering acceptance.

Only the supplied JSON packet is read. Source references are opaque declarations,
not paths to open or URLs to fetch. No evaluator, solver or project store is run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from physimesh.drone.models import project_from_mapping, readiness
from physimesh.projects.contracts import bound_mission

MAX_BYTES = 1_048_576
PURPOSES = ('screening', 'cfd_run', 'feasibility')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


def _constant(_value):
    raise ValueError('nonfinite_number')


def _bounds(value, depth=0, budget=None):
    budget = [20_000] if budget is None else budget
    budget[0] -= 1
    if depth > 32 or budget[0] < 0:
        raise ValueError('structure_limit')
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('nonfinite_number')
    if isinstance(value, dict):
        for child in value.values():
            _bounds(child, depth + 1, budget)
    elif isinstance(value, list):
        for child in value:
            _bounds(child, depth + 1, budget)


def load_packet(path):
    """Reject symlinks/devices, oversized JSON, duplicate keys and nonfinite values."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('regular_file_required')
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('input_size_limit')
    packet = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    _bounds(packet)
    return packet


def _state(value):
    if value is None or value == '' or value == [] or value == {}:
        return 'missing'
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ('unknown', 'unsupported'):
            return text
        return 'present' if text else 'missing'
    if isinstance(value, bool):
        return 'unsupported'
    if isinstance(value, (dict, list)):
        states = [_state(item) for item in (value.values() if isinstance(value, dict) else value)]
        for state in ('unsupported', 'unknown', 'missing'):
            if state in states:
                return state
        return 'present'
    if isinstance(value, (int, float)):
        return 'present' if math.isfinite(value) else 'unsupported'
    return 'unsupported'


def inspect_packet(packet):
    """Return allowlisted paths/counts only; never exception text or client values."""
    _bounds(packet)
    if not isinstance(packet, dict) or packet.get('schema_version') != 'intake_inventory_v1':
        raise ValueError('invalid_packet_schema')
    project = packet.get('project')
    snapshot = project_from_mapping(project)
    inventory = packet.get('inventory', {})
    if not isinstance(inventory, dict):
        raise TypeError('invalid_inventory_schema')
    findings = []

    def check(path, value, *, text=False):
        state = _state(value)
        if text and state == 'present' and not isinstance(value, str):
            state = 'unsupported'
        if state != 'present':
            findings.append({'path': path, 'state': state})
        return state == 'present'

    def record(name, fields):
        raw = inventory.get(name)
        if not isinstance(raw, dict):
            check('inventory.' + name, raw)
            if _state(raw) == 'present':
                findings.append({'path': 'inventory.' + name, 'state': 'unsupported'})
            raw = {}
        for field in fields:
            check(f'inventory.{name}.{field}', raw.get(field),
                  text=field.endswith('_ref') or field in ('units', 'body_frame', 'world_frame',
                                                         'pack_mode', 'reserve_convention'))
        return raw

    def binding(path, supplied, actual):
        if _state(supplied) == 'present' and (supplied != actual or _state(actual) != 'present'):
            findings.append({'path': path, 'state': 'unsupported'})

    geometry = record('geometry', ('source_ref', 'revision_sha256', 'units', 'body_frame',
                                   'world_frame', 'component_roles', 'transforms', 'installation_context'))
    binding('inventory.geometry.revision_sha256', geometry.get('revision_sha256'),
            snapshot.assembly.get('geometry_revision_sha256'))
    for field, actual_key in (('units', 'source_units'), ('body_frame', 'body_frame'), ('world_frame', 'world_frame')):
        binding('inventory.geometry.' + field, geometry.get(field), snapshot.units_and_frames.get(actual_key))
    binding('inventory.geometry.transforms', geometry.get('transforms'), project['units_and_frames'].get('cad_transform'))
    components = project['assembly'].get('components', [])
    roles = ([{'component_id': c.get('component_id'), 'role': c.get('role')} for c in components]
             if isinstance(components, list) and all(isinstance(c, dict) for c in components) else [])
    binding('inventory.geometry.component_roles', geometry.get('component_roles'), roles)

    def bound_records(name, actual, id_key, fields):
        declared = inventory.get(name)
        if not isinstance(declared, list) or not declared:
            check('inventory.' + name, declared)
            if _state(declared) == 'present':
                findings.append({'path': 'inventory.' + name, 'state': 'unsupported'})
            declared = []
        actual_ids = [entry.get(id_key) for entry in actual]
        declared_ids = [entry.get(id_key) if isinstance(entry, dict) else None for entry in declared]
        if (not actual_ids or actual_ids != declared_ids or any(_state(item) != 'present' for item in actual_ids)
                or len(set(map(str, actual_ids))) != len(actual_ids)):
            findings.append({'path': 'inventory.' + name + '.snapshot_binding', 'state': 'unsupported'})
        for index, entry in enumerate(declared):
            entry = entry if isinstance(entry, dict) else {}
            for field in (id_key, *fields):
                check(f'inventory.{name}[{index}].{field}', entry.get(field),
                      text=field.endswith('_ref') or field in (id_key, 'units', 'power_basis'))
        return declared

    rotors = bound_records('rotors', project['rotors'], 'rotor_id',
                          ('map_ref', 'raw_source_ref', 'conditions', 'coverage', 'units',
                           'uncertainty', 'power_basis', 'continuous_burst_duty', 'source_rights'))
    for index, rotor in enumerate(rotors):
        if isinstance(rotor, dict) and index < len(project['rotors']):
            binding(f'inventory.rotors[{index}].map_ref', rotor.get('map_ref'), project['rotors'][index].get('map_ref'))
    masses = project['masses'].get('items', [])
    if not isinstance(masses, list) or any(not isinstance(item, dict) for item in masses):
        masses = []
    bound_records('mass_cg', masses, 'name', ('mass_source_ref', 'cg_source_ref', 'uncertainty', 'placement_envelope'))
    electrical = record('electrical', ('source_ref', 'pack_mode', 'capacity_energy', 'voltage_current_power_limits',
                                      'discharge_temperature_limits', 'motor_esc_continuous_burst_limits',
                                      'efficiency_source_ref', 'auxiliary_demand'))
    mission = record('mission', ('source_ref', 'case_ids', 'segment_ids', 'reserve_convention', 'atmosphere_source_ref'))
    try:
        contract = bound_mission(project)
        mission_state = 'bound_declaration'
        binding('inventory.mission.case_ids', mission.get('case_ids'), [case.case_id for case in contract.cases])
        binding('inventory.mission.segment_ids', mission.get('segment_ids'), [segment.segment_id for segment in contract.sequence])
        binding('inventory.mission.reserve_convention', mission.get('reserve_convention'), contract.reserve_convention)
        binding('inventory.electrical.pack_mode', electrical.get('pack_mode'), contract.pack_mode)
    except Exception:  # noqa: BLE001 - never emit confidential validation exception text
        mission_state = 'missing_or_invalid_bound_declaration'
        findings.append({'path': 'project.mission.contract_definition', 'state': 'unsupported'})
    owners = record('tolerance_ownership', ('engineer_name', 'independent_approver_name', 'intended_claim',
                                          'model_installation_envelope', 'comparison_sources',
                                          'tolerance_policy_source_ref', 'uncertainty_policy_source_ref'))
    for field in ('engineer_name', 'independent_approver_name'):
        check('inventory.tolerance_ownership.' + field, owners.get(field), text=True)
    purposes = {}
    for purpose in PURPOSES:
        try:
            report = readiness(snapshot, purpose)
            purposes[purpose] = {'state': 'inputs_present' if report.ready else 'inputs_incomplete',
                                 'blocking_count': len(report.blocking), 'warning_count': len(report.warnings)}
        except Exception:  # noqa: BLE001 - malformed nested input may throw in existing contract
            purposes[purpose] = {'state': 'unsupported_input_structure', 'blocking_count': None, 'warning_count': None}
    findings = [dict(items) for items in dict.fromkeys(tuple(item.items()) for item in findings)]
    return {'schema_version': 'intake_readiness_receipt_v1',
            'canonical_packet_sha256': hashlib.sha256(json.dumps(packet, sort_keys=True,
                separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest(),
            'inventory_state': 'complete_declarations' if not findings else 'incomplete_declarations',
            'findings': findings, 'purpose_input_readiness': purposes, 'mission_contract': mission_state,
            'source_verification': 'not_performed', 'human_ownership': 'self_declared_not_authenticated',
            'model_acceptance': 'not_assessed', 'engineering_acceptance': 'not_assessed',
            'flight_readiness': 'not_assessed'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = inspect_packet(load_packet(args.input))
        encoded = json.dumps(receipt, indent=2, allow_nan=False) + '\n'
        # Exclusive ownership: existing receipts/symlinks are never overwritten.
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(encoded)
    except Exception:  # noqa: BLE001 - sanitized fixed CLI error, no secrets/path leakage
        print('intake_readiness_failed: invalid input or unavailable new output', file=sys.stderr)
        return 2
    print('intake receipt created; declarations only, no engineering acceptance')
    return 0 if receipt['inventory_state'] == 'complete_declarations' else 1


if __name__ == '__main__':
    raise SystemExit(main())
