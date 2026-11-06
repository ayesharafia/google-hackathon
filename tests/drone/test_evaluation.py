import copy

import pytest

from physimesh.drone.evaluation import evaluate_request, model_catalog
from physimesh.drone.standard_atmosphere import MODEL_ID, standard_atmosphere

CONFIGS = ['multirotor','coaxial','helicopter','fixed_wing','hybrid_vtol','tiltrotor','lift_plus_cruise','custom']
def request(**changes):
    result = {'configuration':'fixed_wing','evaluation':'atmosphere','altitude_m':20000,'altitude_kind':'geopotential'}
    result.update(changes)
    return result
@pytest.mark.parametrize('configuration', CONFIGS)
def test_reference_only_for_any_configuration(configuration):
    r=evaluate_request(request(configuration=configuration))
    assert r['status']=='REFERENCE_COMPUTED'
    assert r['model_id']==MODEL_ID and r['feasibility'] is None
    expected=standard_atmosphere(20000,altitude_kind='geopotential')
    assert r['outputs']=={k:getattr(expected,k) for k in ['pressure_pa','temperature_k','density_kg_m3']}
@pytest.mark.parametrize('field', ['configuration','evaluation','altitude_m','altitude_kind'])
def test_missing(field):
    q=request();del q[field]
    assert evaluate_request(q)['status']=='INPUT_INCOMPLETE'
@pytest.mark.parametrize('value', [True,False,'20000',None,float('nan'),float('inf'),-1,30001,{},[]])
def test_bad_altitude(value):
    r=evaluate_request(request(altitude_m=value))
    assert r['status'] in ['INPUT_INCOMPLETE','MODEL_INAPPLICABLE'] and not r['outputs']
@pytest.mark.parametrize('evaluation', ['aircraft_feasibility','rotor_thrust','wing_lift','structural_stress','thermal','anything'])
def test_no_unimplemented_claim(evaluation):
    r=evaluate_request(request(evaluation=evaluation))
    assert r['status']=='SOLVER_UNSUPPORTED' and r['feasibility'] is None and not r['outputs']
@pytest.mark.parametrize('changes', [ {'configuration':'unknown'}, {'altitude_kind':'pressure'}, {'outputs':['lift_N']}, {'outputs':[]}, {'outputs':['pressure_pa','pressure_pa']}, {'outputs':'pressure_pa'}, {'outputs':[{}]}, {'model_id':'arbitrary'}, {'configuration':[]}, {'evaluation':{}}, {'altitude_kind':[]} ])
def test_malformed_or_unsupported_input(changes):
    r=evaluate_request(request(**changes));assert r['status']!='REFERENCE_COMPUTED' and not r['outputs']
@pytest.mark.parametrize('value', [None, [], 1, 'atmosphere'])
def test_bad_request(value):
    assert evaluate_request(value)['status']!='REFERENCE_COMPUTED'
def test_subset_and_no_mutation():
    q=request(outputs=['density_kg_m3']);old=copy.deepcopy(q)
    r=evaluate_request(q);assert set(r['outputs'])=={'density_kg_m3'} and q==old
@pytest.mark.parametrize('altitude', [0,11000,20000,30000])
@pytest.mark.parametrize('kind',['geometric','geopotential'])
def test_boundary_matches_bound_adapter(altitude,kind):
    r=evaluate_request(request(altitude_m=altitude,altitude_kind=kind))
    assert r['status']=='REFERENCE_COMPUTED'
    assert r['outputs']['pressure_pa']==standard_atmosphere(altitude,altitude_kind=kind).pressure_pa
def test_catalog_is_not_mutable_shared_state():
    a=model_catalog();before=copy.deepcopy(a)
    if isinstance(a,dict):a.clear()
    else:a.clear()
    assert model_catalog()==before
