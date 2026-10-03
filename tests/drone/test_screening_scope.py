from copy import deepcopy

import pytest

from physimesh.core.artifacts import ArtifactStore
from physimesh.drone.demo_screening import example_request
from physimesh.drone.screening_scope import case_scope, pack_consistency


def example(tmp_path):
    return example_request(ArtifactStore(tmp_path/'artifacts'))['project']


def test_pack_energy_hand_calculation_and_reserve_once(tmp_path):
    project = example(tmp_path)
    result = pack_consistency(project)
    assert result['status'] == 'consistent'
    assert result['derived_usable_energy_j'] == 11_520_000
    assert result['pack_mass_kg'] == 20
    project['mission']['energy_system']['usable_energy_j'] = 20*250*.8*3600
    assert pack_consistency(project)['status'] == 'inconsistent'


@pytest.mark.parametrize('field,value', [('usable_fraction', 1.1), ('pack_wh_per_kg', -1),
                                         ('pack_mass_item_names', ['frame']), ('pack_mass_item_names', ['battery', 'battery'])])
def test_unsupported_pack_parameters_refused(tmp_path, field, value):
    project = example(tmp_path)
    project['mission']['energy_system'][field] = value
    assert pack_consistency(project)['status'] == 'inputs_incomplete'


def test_mass_change_cannot_keep_old_pack_energy(tmp_path):
    project = example(tmp_path)
    project['masses']['items'][2]['mass_kg'] = 10
    assert pack_consistency(project)['derived_usable_energy_j'] == 5_760_000
    assert pack_consistency(project)['status'] == 'inconsistent'


def test_acceleration_example_is_a_short_instantaneous_margin(tmp_path):
    project = example(tmp_path)
    case = project['mission']['cases'][1]
    assert case['analysis_scope'] == 'instantaneous_vertical_margin'
    assert case['kind'] == 'acceleration_margin'
    assert case['duration_s'] == 2
    assert case['acceleration_target_m_s2'][2]*case['duration_s'] == 1.2
    assert not case_scope(case, project['rotors'])


@pytest.mark.parametrize('change', ['tilt', 'axis', 'sideways', 'accelerating_steady', 'unknown_scope'])
def test_unsupported_vertical_scope_refused(tmp_path, change):
    project = example(tmp_path)
    case, rotors = deepcopy(project['mission']['cases'][0]), deepcopy(project['rotors'])
    if change == 'tilt':
        case['attitude_deg_zyx'][1] = 10
    elif change == 'axis':
        rotors[0]['axis_body'] = [0.1, 0, 0.994987437]
    elif change == 'sideways':
        case['velocity_world_m_s'][0] = 1
    elif change == 'accelerating_steady':
        case['acceleration_target_m_s2'][2] = .6
    else:
        case.pop('analysis_scope')
    assert case_scope(case, rotors)


def test_long_acceleration_margin_cannot_recreate_a_constant_climb_trajectory(tmp_path):
    project = example(tmp_path)
    case = project['mission']['cases'][1]
    case['duration_s'] = 180
    assert any('at most 2 s' in issue for issue in case_scope(case, project['rotors']))


def test_malformed_pack_selection_returns_a_structured_refusal():
    assert pack_consistency({'mission': {'energy_system': {}, 'reserve_policy': {}}, 'masses': {'items': [None]}})['status'] == 'inputs_incomplete'
