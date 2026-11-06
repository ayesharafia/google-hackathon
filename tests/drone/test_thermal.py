import copy
import math

import pytest

from physimesh.drone.thermal import screen_thermal


def segment(**changes):
    return {'duration_s':100,'ambient_temperature_k':300,'heat_input_w':0,'conductance_w_k':10}|changes


def request(**changes):
    return {'evaluation':'lumped_thermal_screening','mass_kg':2,'specific_heat_j_kg_k':500,'initial_temperature_k':400,'lumped_biot_number':0.05,'property_source':'Synthetic constant-property declaration','segments':[segment()]}|changes


def refusal(body,status='MODEL_INAPPLICABLE'):
    r=screen_thermal(body);assert r['status']==status
    assert r['outputs']=={} and r['output_units']=={}
    assert r['evidence_level']=='unverified' and r['aircraft_status'] is None and r['feasibility'] is None
    return r


def test_cooling_oracle_conservation_nonmutation():
    body=request();before=copy.deepcopy(body);r=screen_thermal(body);assert body==before
    assert r['status']=='SCREENING_COMPUTED'
    o=r['outputs'];s=o['segments'][0]
    assert o['final_temperature_k']==pytest.approx(300+100/math.e,rel=1e-14)
    assert o['maximum_temperature_k']==400 and o['elapsed_s']==100
    assert s['heat_input_j']==0
    assert s['convective_exchange_j']==pytest.approx(100000*(1-1/math.e))
    assert s['thermal_storage_change_j']==pytest.approx(-100000*(1-1/math.e))
    assert abs(s['energy_balance_residual_j'])<1e-8
    assert abs(o['total_energy_balance_residual_j'])<1e-8
    assert r['limitations'] and r['evidence_level']=='unverified'
    assert r['aircraft_status'] is None and r['feasibility'] is None


def test_adiabatic_and_steady_generation():
    r=screen_thermal(request(initial_temperature_k=300,segments=[segment(duration_s=20,heat_input_w=100,conductance_w_k=0)]))
    o=r['outputs'];assert o['final_temperature_k']==302
    assert o['total_heat_input_j']==2000 and o['total_convective_exchange_j']==0
    steady=screen_thermal(request(segments=[segment(heat_input_w=1000)]))['outputs']
    assert steady['final_temperature_k']==400
    assert steady['total_convective_exchange_j']==pytest.approx(100000)
    assert steady['total_storage_change_j']==0


def test_semigroup_signs_and_segment_chronology():
    a=screen_thermal(request())['outputs']
    b=screen_thermal(request(segments=[segment(duration_s=50),segment(duration_s=50)]))['outputs']
    assert b['final_temperature_k']==pytest.approx(a['final_temperature_k'],rel=1e-14)
    assert b['segments'][1]['start_temperature_k']==b['segments'][0]['end_temperature_k']
    assert b['segments'][1]['cumulative_elapsed_s']==100
    heat=screen_thermal(request(initial_temperature_k=250))['outputs']
    assert heat['total_convective_exchange_j']<0 and heat['final_temperature_k']>250
    assert heat['maximum_temperature_k']==heat['final_temperature_k']


@pytest.mark.parametrize('key',['mass_kg','specific_heat_j_kg_k','initial_temperature_k'])
@pytest.mark.parametrize('value',[None,True,'1',0,-1,float('nan'),float('inf'),10**10000],ids=['none','bool','string','zero','negative','nan','inf','huge'])
def test_bad_positive(key,value):
    refusal(request(**{key:value}))


@pytest.mark.parametrize('value',[None,True,'0.1',-1,0.100001,float('nan'),float('inf')])
def test_bad_biot(value):
    refusal(request(lumped_biot_number=value))


def test_keys_shape_source_segments():
    for bad in [None,[],{},True]:refusal(bad)
    for key in request():
        body=request();del body[key];refusal(body)
    refusal(request(extra=1));refusal(request(evaluation='thermal_safety'),'SOLVER_UNSUPPORTED')
    for source in ['', ' ', 'x'*2001, None]:refusal(request(property_source=source))
    for bad in [None,{},[],[segment()]*129,[None],[segment(extra=1)]]:refusal(request(segments=bad))
    for key in segment():
        body=segment();del body[key];refusal(request(segments=[body]))
    for key in segment():
        for bad in [True,'1',None,float('inf'),float('nan'),-1]:refusal(request(segments=[segment(**{key:bad})]))
    for key in ['duration_s','ambient_temperature_k']:
        refusal(request(segments=[segment(**{key:0})]))


def test_small_x_and_extreme_rejection():
    s=screen_thermal(request(segments=[segment(duration_s=1e-9,heat_input_w=1000)]))
    assert s['status']=='SCREENING_COMPUTED'
    o=s['outputs'];assert math.isfinite(o['final_temperature_k'])
    # At equilibrium convection and input cancel even at tiny x.
    assert abs(o['total_energy_balance_residual_j'])<1e-15
    for changes in [{'mass_kg':1e308,'specific_heat_j_kg_k':1e308},{'mass_kg':1e-300,'specific_heat_j_kg_k':1e-300},{'segments':[segment(duration_s=1e308,heat_input_w=1e308)]}]:refusal(request(**changes))


def test_finite_large_integer_and_type_gate():
    body=request(mass_kg=2**1023,specific_heat_j_kg_k=2**-1023,segments=[segment(duration_s=0.1)])
    result=screen_thermal(body)
    assert result['status']=='SCREENING_COMPUTED'
    assert result['outputs']['final_temperature_k']==pytest.approx(300+100/math.e,rel=1e-14)
    for value in [True,None,[],{}]:
        refusal(request(evaluation=value),'SOLVER_UNSUPPORTED')


def test_late_bad_segment_does_not_leak_partial_result():
    refusal(request(segments=[segment(),segment(duration_s=-1)]))


def test_boundary_biot_and_max_segment_count():
    for value in [0,0.1]:
        assert screen_thermal(request(lumped_biot_number=value))['status']=='SCREENING_COMPUTED'
    r=screen_thermal(request(segments=[segment(heat_input_w=1000)]*128))
    assert r['status']=='SCREENING_COMPUTED' and len(r['outputs']['segments'])==128


def test_tiny_unequilibrated_resolution_loss_refuses():
    refusal(request(segments=[segment(duration_s=1e-300)]))


def test_residual_is_computed_not_coerced_to_zero():
    r=screen_thermal(request(segments=[segment(duration_s=0.002,heat_input_w=3)]))
    s=r['outputs']['segments'][0]
    assert s['energy_balance_residual_j']==s['heat_input_j']-s['thermal_storage_change_j']-s['convective_exchange_j']
    assert s['energy_balance_residual_j']!=0


def test_review_underflow_must_not_claim_false_equilibrium():
    body=request(mass_kg=1e200,specific_heat_j_kg_k=1,initial_temperature_k=2e-300,
        property_source='adversarial synthetic declaration',segments=[segment(duration_s=1e300,ambient_temperature_k=1e-300,heat_input_w=0,conductance_w_k=1e-100)])
    result=screen_thermal(body)
    if result['status']=='SCREENING_COMPUTED':
        expected=(1+math.exp(-1))*1e-300
        actual=result['outputs']['final_temperature_k']
        assert math.isclose(actual,expected,rel_tol=1e-14,abs_tol=0)
        row=result['outputs']['segments'][0]
        assert row['thermal_storage_change_j']<0
        assert abs(row['energy_balance_residual_j'])<=1e-12*abs(row['convective_exchange_j'])
    else:
        assert result['status']=='MODEL_INAPPLICABLE' and result['outputs']=={} and result['output_units']=={}


def test_review_subnormal_capacity_must_not_share_wrong_rounded_model():
    body=request(mass_kg=1e-200,specific_heat_j_kg_k=3e-124,initial_temperature_k=300,lumped_biot_number=0,
        segments=[segment(duration_s=1,ambient_temperature_k=300,heat_input_w=5e-324,conductance_w_k=0)])
    result=screen_thermal(body)
    if result['status']=='SCREENING_COMPUTED':
        assert math.isclose(result['outputs']['final_temperature_k'],301.6468854861374885,rel_tol=1e-14,abs_tol=0)
    else:
        assert result['status']=='MODEL_INAPPLICABLE' and result['outputs']=={} and result['output_units']=={}


def test_extreme_cooling_positive_sum_not_cancellation():
    body=request(mass_kg=1.2482925348561917e-250,specific_heat_j_kg_k=5.80327603058309e56,
        initial_temperature_k=1.4864449279761443e-62,segments=[segment(duration_s=5.775511773633764e-64,
        ambient_temperature_k=1.8865570570127386e-126,heat_input_w=1.1392790613298743e-173,conductance_w_k=2.2436439132267876e-60)])
    result=screen_thermal(body)
    if result['status']=='SCREENING_COMPUTED':
        assert math.isclose(result['outputs']['final_temperature_k'],5.0778069310107104e-114,rel_tol=1e-12,abs_tol=0)
    else:
        assert result['status']=='MODEL_INAPPLICABLE' and result['outputs']=={}


def test_review_exponential_underflow_cannot_erase_representable_product():
    body=request(mass_kg=1,specific_heat_j_kg_k=1,initial_temperature_k=1e300,
        segments=[segment(duration_s=750,ambient_temperature_k=1e-100,heat_input_w=0,conductance_w_k=1)])
    result=screen_thermal(body)
    if result['status']=='SCREENING_COMPUTED':
        assert math.isclose(result['outputs']['final_temperature_k'],1.90168496347500654e-26,rel_tol=1e-12,abs_tol=0)
    else:
        assert result['status']=='MODEL_INAPPLICABLE' and result['outputs']=={} and result['output_units']=={}


@pytest.mark.parametrize('duration',[700,708,709,740,745,746,750,800])
def test_exponential_range_boundary_and_scaling(duration):
    from decimal import Decimal, localcontext
    for scale in [1,10]:
        body=request(mass_kg=scale,specific_heat_j_kg_k=1,initial_temperature_k=1e300,
            segments=[segment(duration_s=duration,ambient_temperature_k=1e-100,heat_input_w=0,conductance_w_k=scale)])
        result=screen_thermal(body)
        if duration>=746:
            assert result['status']=='MODEL_INAPPLICABLE' and result['outputs']=={} and result['output_units']=={}
            assert result['evidence_level']=='unverified' and result['aircraft_status'] is None and result['feasibility'] is None
        elif result['status']=='SCREENING_COMPUTED':
            with localcontext() as ctx:
                ctx.prec=120
                expected=float(Decimal.from_float(1e300)*(-Decimal(duration)).exp()+Decimal.from_float(1e-100)*(1-(-Decimal(duration)).exp()))
            assert math.isclose(result['outputs']['final_temperature_k'],expected,rel_tol=1e-12,abs_tol=0)
        else:
            assert result['status']=='MODEL_INAPPLICABLE' and result['outputs']=={} and result['output_units']=={}


def test_large_integer_original_cooling_outside_supported_exponential_range():
    refusal(request(mass_kg=2**1023,specific_heat_j_kg_k=2**-1023))
