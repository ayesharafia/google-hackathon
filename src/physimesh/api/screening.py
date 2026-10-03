"""Payload screening with snapshot-bound retained performance and limit records."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, fields

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from physimesh.core.artifacts import ArtifactStore
from physimesh.drone.mass import MassItem, summarize
from physimesh.drone.models import project_from_mapping, readiness
from physimesh.drone.screening import CapacityCaseInput, RotorLimitPoint, capacity_from_cases
from physimesh.drone.screening_diagnostics import diagnostics
from physimesh.drone.screening_scope import case_scope, pack_consistency
from physimesh.drone.snapshot_hash import snapshot_sha256

router = APIRouter(prefix='/api/drone')


class ScreeningRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project: dict
    approved_design_sha256: str | None = None
    case_inputs: list[dict] = []
    usable_energy_j: float | None = None


def _blocked(blocking, *, category='inputs_incomplete', code='missing_or_invalid_input', **details):
    return {'max_payload_kg': None, 'limiting_case_id': None, 'cases': [],
            'empty_airframe_mass_kg': None, 'status': 'inputs_incomplete', 'blocking': blocking,
            'outcome': category, 'trim_eligibility': 'not_evaluated',
            'reasons': [{'category': category, 'code': code, 'detail': item} for item in blocking],
            'interpretation': 'Capacity unavailable until every declared design, case and operating limit is complete.',
            **details}


@router.post('/screening')
def screening(request: Request, body: ScreeningRequest):
    try:
        snapshot = project_from_mapping(body.project)
    except (TypeError, ValueError) as exc:
        return _blocked([f'invalid project: {exc}'])
    check = readiness(snapshot, 'screening')
    try:
        design_hash = snapshot_sha256(body.project)
    except (TypeError, ValueError, OverflowError) as exc:
        return _blocked([f'invalid project provenance: {exc}'])
    blocking = list(check.blocking)
    if body.approved_design_sha256 != design_hash:
        blocking.append('approved_design_sha256: caller approval must bind this exact project snapshot')
    declared = snapshot.mission.get('cases')
    if not declared or any(not isinstance(case, Mapping) for case in declared):
        return _blocked(['mission.cases: named case mappings required'])
    if not declared:
        blocking.append('mission.cases: required mission cases must be declared')
    names = [case.get('name') for case in declared or ()]
    if any(not isinstance(name, str) or not name.strip() for name in names) or len(set(names)) != len(names):
        blocking.append('mission.cases: unique named cases required')
    if blocking:
        return _blocked(blocking)
    store = ArtifactStore(request.app.state.settings.data_root/'artifacts')
    conditions = {case['name']: snapshot_sha256(dict(case)) for case in declared}
    energy = snapshot.mission.get('energy_system')
    if not isinstance(energy, Mapping) or body.usable_energy_j != energy.get('usable_energy_j'):
        return _blocked(['mission.energy_system.usable_energy_j: explicit approved energy limit required'])
    pack = pack_consistency(body.project)
    if pack['status'] != 'consistent':
        return _blocked(['Battery mass and usable energy must agree with the approved pack parameters.'],
                        code=pack['code'], pack_consistency=pack)
    scope_issues = [issue for case in declared for issue in case_scope(case, snapshot.rotors)]
    if scope_issues:
        return _blocked(scope_issues, category='unsupported_scope', code='trim_or_scope_unresolved')
    ids = [rotor.get('rotor_id') for rotor in snapshot.rotors]
    if any(not isinstance(identifier, str) or not identifier.strip() for identifier in ids) or len(set(ids)) != len(ids):
        return _blocked(['rotors: unique string rotor IDs required'])
    rotor_by_id = {rotor.get('rotor_id'): rotor for rotor in snapshot.rotors}
    rotor_ids = {rotor.get('rotor_id') for rotor in snapshot.rotors}
    known_mass_keys = {field.name for field in fields(MassItem)}
    mass = summarize([MassItem(**{k: v for k, v in item.items() if k in known_mass_keys})
                      for item in snapshot.masses['items']])
    inputs = []

    def bind_source(digest, expected, prefix):
        try:
            with store.open(digest) as stream:
                raw = stream.read()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('artifact hash changed')
            record = json.loads(raw)
            if not isinstance(record, dict) or any(record.get(key) != value for key, value in expected.items()):
                raise ValueError('source values or snapshot/condition binding differ')
        except (KeyError, TypeError, ValueError, OSError) as exc:
            blocking.append(f'{prefix}: retained source unavailable or inconsistent ({exc})')

    for raw_case in body.case_inputs:
        try:
            raw_rotors = raw_case['rotors']
            rotors = tuple(RotorLimitPoint(**rotor) for rotor in raw_rotors)
            case = CapacityCaseInput(**{**raw_case, 'rotors': rotors})
            if case.case_id not in conditions:
                blocking.append(f'case {case.case_id}: absent from approved mission')
                continue
            if {rotor.rotor_id for rotor in rotors} != rotor_ids or len(rotors) != len(rotor_ids):
                blocking.append(f'case {case.case_id}: performance required for every declared rotor')
            declared_case = next(item for item in declared if item['name'] == case.case_id)
            acceleration = declared_case.get('acceleration_target_m_s2')
            if not acceleration or len(acceleration) != 3 or case.vertical_acceleration_m_s2 != acceleration[2]:
                blocking.append(f'case {case.case_id}: acceleration differs from approved mission')
            duration = declared_case.get('duration_s', snapshot.mission.get('duration_s'))
            if case.duration_s != duration:
                blocking.append(f'case {case.case_id}: duration differs from approved mission')
            if case.available_electrical_power_w != energy.get('available_electrical_power_w'):
                blocking.append(f'case {case.case_id}: available power must match approved energy-system limit')
            common = {'design_snapshot_sha256': design_hash, 'case_sha256': conditions[case.case_id]}
            bind_source(case.body_force_source_sha256,
                        {**common, 'schema': 'body_force_v1', 'body_force_world_n': list(case.body_force_world_n)},
                        f'case {case.case_id} body force')
            for rotor in rotors:
                declared_limits = rotor_by_id.get(rotor.rotor_id, {}).get('sustained_limits')
                if (not isinstance(declared_limits, Mapping) or
                        rotor.sustained_electrical_power_limit_w != declared_limits.get('electrical_power_w')):
                    blocking.append(f'rotor {rotor.rotor_id}: sustained power differs from approved limits')
                bind_source(rotor.performance_source_sha256,
                            {**common, 'schema': 'rotor_limit_point_v1', 'rotor_id': rotor.rotor_id,
                             'force_world_n': list(rotor.force_world_n), 'electrical_power_w': rotor.electrical_power_w},
                            f'case {case.case_id} rotor {rotor.rotor_id} performance')
                bind_source(rotor.limit_source_sha256,
                            {'design_snapshot_sha256': design_hash, 'schema': 'sustained_limit_v1',
                             'rotor_id': rotor.rotor_id,
                             'sustained_electrical_power_limit_w': rotor.sustained_electrical_power_limit_w},
                            f'rotor {rotor.rotor_id} limits')
            inputs.append(case)
        except (KeyError, TypeError, ValueError) as exc:
            blocking.append(f'case input malformed: {exc}')
    if blocking:
        return _blocked(blocking)
    try:
        report = capacity_from_cases(mass, names, inputs, usable_energy_j=body.usable_energy_j)
    except (TypeError, ValueError, OverflowError) as exc:
        return _blocked([f'invalid capacity inputs: {exc}'])
    result = asdict(report)
    result['status'] = report.status.value
    result['rotor_diagnostics'] = diagnostics(body.project, body.case_inputs)
    result['approved_design_sha256'] = design_hash
    result['pack_consistency'] = pack
    result['case_scope'] = [{'case_id': case['name'], 'analysis_scope': case['analysis_scope'],
                             'duration_s': case.get('duration_s', snapshot.mission.get('duration_s')),
                             'trajectory_evaluated': False} for case in declared]
    result['assumptions'] = ['World-vertical force ceiling at supplied sustained limits; trim and structure pending.',
                             'Cases are alternative operating conditions; energies checked independently.',
                             'Electrical power and usable energy are supplied data, not physically validated; limit checks alone do not prove operability.',
                             'Isolated ideal-hover power is a diagnostic; ground effect and rotor interference are not modelled.',
                             'Rotor performance must already include environment, attitude and reserve policy.']
    result['assumptions'] += ['Constant-point force and energy screening only; no trajectory or sequential mission integration.',
                              'Acceleration margin uses force at the supplied instantaneous velocity; its duration is an illustrative constant-power energy check.',
                              'Trim eligibility: geometry/conditions meet the restricted vertical screen, but moment balance, control allocation and payload CG remain unevaluated.']
    return result


@router.get('/examples/screening')
def example(request: Request):
    path = request.app.state.settings.data_root/'examples/screening.json'
    if not path.is_file():
        raise HTTPException(404, 'example records have not been seeded')
    return json.loads(path.read_text())


@router.get('/project-template')
def project_template():
    from pathlib import Path

    import yaml

    from physimesh.drone import models
    return yaml.safe_load(Path(models.__file__).with_name('schema').joinpath('drone_manifest_v1.yaml').read_text())
