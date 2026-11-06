import copy
import math

import pytest

from physimesh.drone.cantilever import screen_cantilever


def request(**changes):
    return {'evaluation':'rectangular_cantilever_screening','length_m':2,'width_m':0.1,'depth_m':0.2,'youngs_modulus_pa':200e9,'tip_load_n':1000,'uniform_load_n_m':0,'property_source':'synthetic isotropic elastic fixture','applicability_declaration':'slender prismatic small-rotation synthetic beam','declared_min_slenderness':10,'declared_max_deflection_ratio':0.01,'declared_max_slope_rad':0.01}|changes


def refusal(body,status='MODEL_INAPPLICABLE'):
    r=screen_cantilever(body)
    assert r['status']==status and r['outputs']=={} and r['output_units']=={}
    assert r['evidence_level']=='unverified' and r['aircraft_status'] is None and r['feasibility'] is None


def test_independent_endload_oracle():
    b=request();before=copy.deepcopy(b);r=screen_cantilever(b);assert b==before
    assert r['status']=='SCREENING_COMPUTED'
    o=r['outputs'];assert o['second_moment_m4']==pytest.approx(1/15000)
    assert o['root_shear_magnitude_n']==1000 and o['root_moment_magnitude_n_m']==2000
    assert o['tip_deflection_m']==pytest.approx(0.0002)
    assert o['tip_slope_rad']==pytest.approx(0.00015)
    assert o['root_outer_fiber_stress_magnitude_pa']==pytest.approx(3e6)
    assert o['slenderness']==10 and o['deflection_ratio']==pytest.approx(0.0001)
    assert r['evidence_level']=='unverified' and r['aircraft_status'] is None and r['feasibility'] is None
    assert r['limitations'] and r['output_units']['tip_deflection_m']=='m'


def test_uniform_and_superposition_zero():
    p=screen_cantilever(request())['outputs'];u=screen_cantilever(request(tip_load_n=0,uniform_load_n_m=100))['outputs'];s=screen_cantilever(request(uniform_load_n_m=100))['outputs']
    assert u['tip_deflection_m']==pytest.approx(0.000015)
    assert u['tip_slope_rad']==pytest.approx(0.00001)
    assert u['root_shear_magnitude_n']==200 and u['root_moment_magnitude_n_m']==200
    for key in ['tip_deflection_m','tip_slope_rad','root_shear_magnitude_n','root_moment_magnitude_n_m','root_outer_fiber_stress_magnitude_pa']:
        assert s[key]==pytest.approx(p[key]+u[key])
    z=screen_cantilever(request(tip_load_n=0))['outputs'];assert z['tip_deflection_m']==0 and z['root_outer_fiber_stress_magnitude_pa']==0


@pytest.mark.parametrize('key',['length_m','width_m','depth_m','youngs_modulus_pa','declared_min_slenderness','declared_max_deflection_ratio','declared_max_slope_rad'])
@pytest.mark.parametrize('value',[0,-1,None,True,'1',float('nan'),float('inf')])
def test_invalid_positive(key,value):refusal(request(**{key:value}))


def test_invalid_shape_declarations_loads_huge():
    for b in [None,[],{},True]:refusal(b)
    for key in request():
        b=request();del b[key];refusal(b)
    refusal(request(extra=1));refusal(request(evaluation='FEM'),'SOLVER_UNSUPPORTED')
    for key in ['property_source','applicability_declaration']:
        for v in ['', ' ', None, 'x'*2001]:refusal(request(**{key:v}))
    for key in ['tip_load_n','uniform_load_n_m']:
        for v in [-1,True,'1',None,float('inf'),float('nan')]:refusal(request(**{key:v}))
    for key in ['length_m','width_m','depth_m','youngs_modulus_pa']:
        refusal(request(**{key:10**10000}))
    for changes in [{'width_m':1e-200,'depth_m':1e-200},{'length_m':1e200},{'tip_load_n':1e308}]:refusal(request(**changes))


def test_declared_gates_only_and_scaling():
    refusal(request(declared_min_slenderness=11));refusal(request(declared_max_deflection_ratio=1e-5));refusal(request(declared_max_slope_rad=1e-5))
    a=screen_cantilever(request())['outputs'];b=screen_cantilever(request(youngs_modulus_pa=400e9))['outputs']
    assert b['tip_deflection_m']==pytest.approx(a['tip_deflection_m']/2)
    assert b['root_outer_fiber_stress_magnitude_pa']==a['root_outer_fiber_stress_magnitude_pa']
    assert math.isfinite(a['tip_slope_rad'])
