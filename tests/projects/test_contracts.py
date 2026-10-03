import json
from pathlib import Path

import pytest

from physimesh.projects.contracts import compatibility_status
from physimesh.projects.serialization import dump_contract, import_legacy_manifest, load_contract

FIXTURES = Path(__file__).with_name('fixtures')


@pytest.mark.parametrize('name', ['old_sphere', 'incomplete_draft', 'approved_synthetic_design',
                                 'infeasible', 'unsupported', 'unresolved', 'detached_review'])
def test_versions_roundtrip_without_changing_status_or_unknown_values(name):
    raw = (FIXTURES/(name+'.json')).read_bytes()
    model = load_contract(raw)
    assert load_contract(dump_contract(model)) == model
    if name == 'old_sphere':
        assert model.evidence == 'unverified' and model.independent_review == 'pending'
    if name == 'incomplete_draft':
        assert json.loads(model.snapshot_json)['mission']['payload_mass_kg'] is None


def data(name):
    return json.loads((FIXTURES/(name+'.json')).read_bytes())


def parse(value):
    return load_contract(json.dumps(value).encode())


def test_draft_cannot_be_approved_by_omitting_readiness_reasons():
    value = data('approved_synthetic_design')
    draft = data('incomplete_draft')
    from physimesh.drone.snapshot_hash import snapshot_sha256
    value['snapshot_json'] = draft['snapshot_json']
    value['snapshot_sha256'] = snapshot_sha256(json.loads(draft['snapshot_json']))
    with pytest.raises(ValueError, match='incomplete method-specific'):
        parse(value)


def test_design_mutation_invalidates_binding_and_content_is_immutable():
    value = data('approved_synthetic_design')
    value['snapshot_sha256'] = '0'*64
    with pytest.raises(ValueError, match='digest differs'):
        parse(value)
    revision = parse(data('approved_synthetic_design'))
    with pytest.raises(ValueError):
        revision.snapshot_json = '{}'


def test_unresolved_and_unsupported_never_become_infeasible_or_get_headline():
    for name in ('unsupported', 'unresolved'):
        value = data(name)
        value['aircraft_status'] = 'requirement_not_met'
        with pytest.raises(ValueError, match='must not imply'):
            parse(value)
        value = data(name)
        value['payload_lower_bound_kg'] = 0
        with pytest.raises(ValueError, match='only feasible'):
            parse(value)
    assert compatibility_status('unresolved', inputs_complete=True) == 'numerically_unverified'
    assert compatibility_status('infeasible', inputs_complete=False) == 'inputs_incomplete'


def feasible(sequence=False):
    value = data('unresolved')
    value.update(physical_outcome='feasible', aircraft_status='screening_only', reasons=[],
                 payload_lower_bound_kg=10.0, limiting_case_id='climb')
    value['cases'] = [{'case_id':'hover','outcome':'feasible','feasible_payload_lower_bound_kg':20.0},
                      {'case_id':'climb','outcome':'feasible','feasible_payload_lower_bound_kg':10.0}]
    if sequence:
        value['spec']['mission']['sequence'] = [
            {'segment_id':'leg-1','case_id':'hover','duration_s':300,'approximation':'constant_point','model_sha256':'9'*64},
            {'segment_id':'leg-2','case_id':'climb','duration_s':2,'approximation':'constant_point','model_sha256':'8'*64}]
    # Unpublished schema fixture only, not evidence of a solved aircraft.
    value.update(publication=None, publication_state='private_staging')
    return value


def test_required_case_coverage_minimum_and_limiting_case_are_checked():
    assert parse(feasible()).payload_lower_bound_kg == 10
    value = feasible(); value['cases'].pop()
    with pytest.raises(ValueError, match='all required'):
        parse(value)
    value = feasible(); value['payload_lower_bound_kg'] = 20
    with pytest.raises(ValueError, match='minimum required'):
        parse(value)
    value = feasible(); value['limiting_case_id'] = 'hover'
    with pytest.raises(ValueError, match='limiting case differs'):
        parse(value)


def test_sequence_requires_its_own_energy_evidence_not_individual_case_passes():
    value = feasible(sequence=True)
    with pytest.raises(ValueError, match='sequence energy'):
        parse(value)
    value['sequence_energy_evidence_sha256'] = '7'*64
    assert len(parse(value).spec.mission.sequence) == 2
    value['spec']['mission']['sequence'][0]['case_id'] = 'missing'
    with pytest.raises(ValueError, match='unknown case'):
        parse(value)


def test_review_cannot_move_across_project_or_revision_and_does_not_promote_evidence():
    result = parse(data('infeasible')); review = parse(data('detached_review'))
    review.assert_applies_to(result)
    assert result.evidence == 'unverified'
    changed = data('detached_review'); changed['project_id'] = 'other'
    with pytest.raises(ValueError, match='exact project'):
        parse(changed).assert_applies_to(result)
    changed = data('detached_review'); changed['package_revision_sha256'] = '0'*64
    with pytest.raises(ValueError, match='exact project'):
        parse(changed).assert_applies_to(result)
    changed = data('detached_review'); changed['authenticated_record_sha256'] = None
    with pytest.raises(ValueError, match='authenticated record'):
        parse(changed)


def test_publication_and_validation_are_distinct_from_completed_execution():
    value = data('infeasible'); value['publication']['study_sha256'] = '0'*64
    with pytest.raises(ValueError, match='different study'):
        parse(value)
    value = data('infeasible'); value['evidence'] = 'validated_for_case_family'
    with pytest.raises(ValueError, match='validation envelope'):
        parse(value)
    value = data('infeasible'); value['execution'] = 'failed'
    with pytest.raises(ValueError, match='complete execution'):
        parse(value)


def test_wire_boundary_rejects_unknown_versions_duplicates_and_nonfinite_numbers():
    with pytest.raises(ValueError, match='unknown contract'):
        load_contract(b'{"schema_version":"aircraft_study_v99"}')
    with pytest.raises(ValueError, match='duplicate JSON key'):
        load_contract(b'{"schema_version":"results_v1","schema_version":"aircraft_study_v2"}')
    value = feasible(); value['payload_lower_bound_kg'] = float('nan')
    with pytest.raises(ValueError, match='nonfinite'):
        parse(value)
    # Pydantic copy bypass is refused on export.
    model = parse(feasible()).model_copy(update={'payload_lower_bound_kg':20.0})
    with pytest.raises(ValueError, match='minimum required'):
        dump_contract(model)


def test_legacy_payload_ambiguity_requires_explicit_interpretation():
    raw = data('approved_synthetic_design')['snapshot_json'].encode()
    with pytest.raises(ValueError, match='confirm installed'):
        import_legacy_manifest(raw, organization_id='org',project_id='project')
    migrated = import_legacy_manifest(raw,organization_id='org',project_id='project',payload_interpretation='installed_mass')
    assert migrated.draft_version == 0 and not hasattr(migrated, 'approval')
    assert migrated.legacy_source_sha256 and migrated.snapshot_json == raw.decode()


def test_design_binding_checks_revision_project_approval_and_method_scope():
    revision = parse(data('approved_synthetic_design'))
    spec = parse(data('infeasible')).spec
    spec.assert_design_binding(revision)
    changed = revision.model_copy(update={'project_id':'other'})
    with pytest.raises(ValueError, match='same-project'):
        spec.assert_design_binding(changed)
    changed = revision.model_copy(update={'approval':'approval_pending'})
    with pytest.raises(ValueError, match='approved'):
        spec.assert_design_binding(changed)
    changed = spec.model_copy(update={'method':'measured_map_trim'})
    with pytest.raises(ValueError, match='applicable readiness'):
        changed.assert_design_binding(revision)


def test_invalid_calendar_timestamp_is_not_accepted_as_review_provenance():
    value = data('detached_review'); value['created_utc'] = '2026-99-32T25:00:00Z'
    with pytest.raises(ValueError):
        parse(value)


def test_feasible_and_unevaluated_statuses_cannot_cross_outcome_or_method_axes():
    value = feasible(); value['aircraft_status'] = 'requirement_not_met'
    with pytest.raises(ValueError, match='feasible status'):
        parse(value)
    value = feasible(); value.update(aircraft_status='within_validated_envelope',
                                    evidence='validated_for_case_family',validation_envelope_sha256='9'*64)
    with pytest.raises(ValueError, match='supplied-point screening'):
        parse(value)
    value = feasible(); value.update(execution='queued',physical_outcome='not_evaluated',
                                    aircraft_status='within_validated_envelope',evidence='validated_for_case_family',
                                    validation_envelope_sha256='9'*64,payload_lower_bound_kg=None,limiting_case_id=None)
    with pytest.raises(ValueError, match='uncompleted execution'):
        parse(value)
    value.update(execution='completed',evidence='unverified',aircraft_status='screening_only')
    with pytest.raises(ValueError, match='unevaluated study'):
        parse(value)


@pytest.mark.parametrize('mutation', ['condition', 'required', 'omitted', 'reserve', 'pack', 'sequence'])
def test_study_mission_cannot_escape_approved_conditions(mutation):
    revision = parse(data('approved_synthetic_design'))
    value = data('infeasible')['spec']
    if mutation == 'condition': value['mission']['cases'][0]['conditions_sha256'] = '0'*64
    if mutation == 'required': value['mission']['cases'][0]['required'] = False
    if mutation == 'omitted': value['mission']['cases'].pop()
    if mutation == 'reserve': value['mission']['reserve_value'] = .1
    if mutation == 'pack': value['mission']['pack_mode'] = 'sized'
    if mutation == 'sequence': value['mission']['sequence'] = [
        {'segment_id':'leg','case_id':'hover','duration_s':300,'approximation':'constant_point','model_sha256':'9'*64}]
    with pytest.raises(ValueError, match='mission differs'):
        parse(value).assert_design_binding(revision)


def test_approved_revision_cannot_bind_conflicting_typed_and_raw_mission():
    from physimesh.drone.provenance import canonical_json
    from physimesh.drone.snapshot_hash import snapshot_sha256
    value = data('approved_synthetic_design')
    snapshot = json.loads(value['snapshot_json'])
    snapshot['mission']['cases'][0]['duration_s'] = 600
    value.update(snapshot_json=canonical_json(snapshot),snapshot_sha256=snapshot_sha256(snapshot))
    with pytest.raises(ValueError, match='condition digest'):
        parse(value)


@pytest.mark.parametrize('fixture', ['infeasible', 'unsupported', 'unresolved'])
def test_screening_cannot_claim_mesh_evidence_even_for_nonfeasible_outcomes(fixture):
    value = data(fixture); value['evidence'] = 'mesh_assessed'
    with pytest.raises(ValueError, match='supplied-point screening'):
        parse(value)


@pytest.mark.parametrize('status', ['inputs_incomplete', 'numerically_unverified', 'requirement_not_met'])
def test_feasible_screening_refuses_contradictory_statuses(status):
    value = feasible(); value['aircraft_status'] = status
    with pytest.raises(ValueError, match='feasible status'):
        parse(value)


def test_review_scope_and_supersession_require_explicit_meaningful_binding():
    value = data('detached_review'); value['scope'] = '  \n '
    with pytest.raises(ValueError, match='meaningful text'):
        parse(value)
    value = data('detached_review'); value['state'] = 'superseded'
    with pytest.raises(ValueError, match='attestation it supersedes'):
        parse(value)
    value['supersedes_attestation_sha256'] = '7'*64
    assert parse(value).state == 'superseded'


def test_aggregate_failure_and_withdrawal_require_reasons_and_retained_identity():
    value = feasible()
    value.update(physical_outcome='infeasible', aircraft_status='requirement_not_met',
                 payload_lower_bound_kg=None, limiting_case_id=None, reasons=data('unresolved')['reasons'])
    with pytest.raises(ValueError, match='aggregate limit reason'):
        parse(value)
    value['reasons'][0]['code'] = 'limit_exceeded'
    assert parse(value).physical_outcome == 'infeasible'
    value['publication_state'] = 'withdrawn'
    with pytest.raises(ValueError, match='retained publication identity'):
        parse(value)


@pytest.mark.parametrize('convention', ['held_energy_j', 'additional_mission_demand'])
def test_approved_reserve_cannot_keep_legacy_fraction_kind_under_other_convention(convention):
    from physimesh.drone.provenance import canonical_json
    from physimesh.drone.snapshot_hash import snapshot_sha256
    value = data('approved_synthetic_design'); snapshot = json.loads(value['snapshot_json'])
    snapshot['mission']['reserve_policy']['convention'] = convention
    snapshot['mission']['contract_definition']['reserve_convention'] = convention
    value.update(snapshot_json=canonical_json(snapshot), snapshot_sha256=snapshot_sha256(snapshot))
    with pytest.raises(ValueError, match='reserve kind disagrees'):
        parse(value)


def test_screening_approval_refuses_other_reserve_model_even_with_matching_units():
    from physimesh.drone.provenance import canonical_json
    from physimesh.drone.snapshot_hash import snapshot_sha256
    value = data('approved_synthetic_design'); snapshot = json.loads(value['snapshot_json'])
    snapshot['mission']['reserve_policy'].update(convention='additional_mission_demand',
                                                kind='additional_mission_demand_fraction')
    snapshot['mission']['contract_definition']['reserve_convention'] = 'additional_mission_demand'
    value.update(snapshot_json=canonical_json(snapshot), snapshot_sha256=snapshot_sha256(snapshot))
    with pytest.raises(ValueError, match='screening supports only'):
        parse(value)
