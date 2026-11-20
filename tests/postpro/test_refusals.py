from physimesh.postpro.refusals import sphere_refusals


def test_sphere_refusals_are_generated_by_engine_with_reasons():
    refusals = sphere_refusals()
    assert {item['request'] for item in refusals} == {'y_plus', 'mean_pressure', 'blade_pressure', 'independent_ranges'}
    assert all(item['rejected'] and item['next_action'] for item in refusals)
    assert any('laminar' in reason for item in refusals for reason in item['rejected'])
    assert any('window' in reason for item in refusals for reason in item['rejected'])
