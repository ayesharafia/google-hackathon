import json
from pathlib import Path

import pytest

from physimesh.drone.authoring import candidate_mass, inspect_inputs


def snapshot():
    raw = json.loads((Path(__file__).parents[1] / 'projects/fixtures/approved_synthetic_design.json').read_text())
    data = json.loads(raw['snapshot_json'])
    data['masses']['items'] = [
        {'name': 'structure', 'category': 'structure', 'mass_kg': 10, 'cg_body_m': [1, 0, 0]},
        {'name': 'battery', 'category': 'energy', 'mass_kg': 2, 'cg_body_m': [0, 0, 0]},
        {'name': 'installed', 'category': 'payload', 'mass_kg': 5, 'cg_body_m': [-1, 0, 0]},
        *[{'name': category, 'category': category, 'mass_kg': 0, 'cg_body_m': [0, 0, 0]}
          for category in ('propulsion', 'avionics', 'other')]]
    return data


def test_payload_replacement_and_relocation_have_independent_weighted_cg():
    data = snapshot()
    result = candidate_mass(data, 3, [2, 0, 0])
    assert result.total_mass_kg == 15  # 10 structure + 2 pack + 3 payload, original 5 excluded.
    assert result.cg_body_m.tolist() == pytest.approx([16 / 15, 0, 0])
    assert result.by_category['energy'] == 2
    assert data['masses']['items'][2]['mass_kg'] == 5


def test_duplicate_mass_name_and_boolean_mass_refuse():
    data = snapshot()
    data['masses']['items'][1]['name'] = 'structure'
    with pytest.raises(ValueError, match='unique'):
        inspect_inputs(data)
    data = snapshot(); data['masses']['items'][0]['mass_kg'] = True
    with pytest.raises(ValueError, match='number'):
        inspect_inputs(data)


def test_pack_keeps_unknown_and_conflicting_energy_visible():
    data = snapshot()
    assert inspect_inputs(data)['pack']['status'] != 'consistent'
    data['mission']['energy_system'] = {'pack_mass_item_names': ['battery'], 'pack_wh_per_kg': 100,
                                        'usable_fraction': .8, 'usable_energy_j': 460800}
    data['mission']['reserve_policy'] = {'kind': 'fraction', 'value': .2,
                                       'convention': 'held_usable_energy_fraction'}
    assert inspect_inputs(data)['pack']['status'] == 'consistent'
    data['mission']['energy_system']['usable_energy_j'] = 500000
    assert inspect_inputs(data)['pack']['status'] == 'inconsistent'
