import math
import sys


def cantilever_values(L, b, h, E, P, q):
    def checked(value, nonzero=False):
        if (not math.isfinite(value)
                or (value != 0.0 and abs(value) < sys.float_info.min)
                or (nonzero and value == 0.0)):
            raise ValueError('Nonfinite, subnormal, or underflowed value')
        return value

    def mul(a, b):
        return checked(a * b, a != 0.0 and b != 0.0)

    def div(a, b):
        return checked(a / b, a != 0.0)

    def add(a, b):
        return checked(a + b, a != 0.0 or b != 0.0)

    try:
        L, b, h, E, P, q = map(float, (L, b, h, E, P, q))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Inputs must be finite real numbers') from exc
    for value in (L, b, h, E, P, q):
        checked(value)
    if any(value <= 0.0 for value in (L, b, h, E)):
        raise ValueError('L, b, h, and E must be positive')
    if P < 0.0 or q < 0.0:
        raise ValueError('P and q must be nonnegative')

    h3 = mul(mul(h, h), h)
    L2 = mul(L, L)
    L3 = mul(L2, L)
    L4 = mul(L3, L)
    I = div(mul(b, h3), 12.0)
    EI = mul(E, I)
    shear = add(P, mul(q, L))
    moment = add(mul(P, L), div(mul(q, L2), 2.0))
    delta = add(div(mul(P, L3), mul(3.0, EI)),
                div(mul(q, L4), mul(8.0, EI)))
    slope = add(div(mul(P, L2), mul(2.0, EI)),
                div(mul(q, L3), mul(6.0, EI)))
    return {
        'second_moment_m4': I,
        'flexural_rigidity_n_m2': EI,
        'root_shear_magnitude_n': shear,
        'root_moment_magnitude_n_m': moment,
        'tip_deflection_m': delta,
        'tip_slope_rad': slope,
        'root_outer_fiber_stress_magnitude_pa': div(mul(moment, h), mul(2.0, I)),
        'slenderness': div(L, h),
        'deflection_ratio': div(delta, L),
    }


FIELDS={'evaluation','length_m','width_m','depth_m','youngs_modulus_pa','tip_load_n','uniform_load_n_m','property_source','applicability_declaration','declared_min_slenderness','declared_max_deflection_ratio','declared_max_slope_rad'}
UNITS=dict(zip(['second_moment_m4','flexural_rigidity_n_m2','root_shear_magnitude_n','root_moment_magnitude_n_m','tip_deflection_m','tip_slope_rad','root_outer_fiber_stress_magnitude_pa','slenderness','deflection_ratio'],['m^4','N*m^2','N','N*m','m','rad','Pa','1','1']))
LIMITATIONS=[
    'Euler-Bernoulli prismatic rectangular beam, constant isotropic linear elasticity, small rotations and ideal fixed root assumed.',
    'Nonnegative tip and uniform loads share one transverse direction; outputs are magnitudes, not a general sign/frame solver.',
    'Material source, slenderness, deflection and rotation limits are caller declarations, not verified applicability or engineering acceptance.',
    'No shear deformation, axial coupling, torsion, buckling, fatigue, joints, aeroelasticity, yield or structural safety assessment.',
    'Analytical screening only, not FEM, mesh convergence, physical validation or aircraft feasibility.',
    'Binary64 derived subnormal, overflow and nonzero underflow states are conservatively refused; no scaled extended-range solver.',
]


def screen_cantilever(request):
    result={'model_id':'rectangular_cantilever_linear_screening_v1','status':'MODEL_INAPPLICABLE','evidence_level':'unverified','aircraft_status':None,'feasibility':None,'outputs':{},'output_units':{},'reasons':[],'limitations':list(LIMITATIONS),'sources':[{'url':'https://mechanics.tamu.edu/wp-content/uploads/2017/03/Appendix-A_Exact-Analytical-Solutions.pdf','scope':'A3 linear beam equation, superposition and cantilever analytical solutions'}]}
    try:
        if type(request) is not dict or set(request)!=FIELDS:
            raise ValueError('Exact request fields required')
        if type(request['evaluation']) is not str or request['evaluation']!='rectangular_cantilever_screening':
            result['status']='SOLVER_UNSUPPORTED'
            raise ValueError('Unsupported evaluation')
        for key in ['property_source','applicability_declaration']:
            if type(request[key]) is not str or not request[key].strip() or len(request[key])>2000:
                raise ValueError('Nonblank source and applicability declarations up to 2000 characters required')
        values={}
        for key in FIELDS-{'evaluation','property_source','applicability_declaration'}:
            value=request[key]
            if type(value) not in (int,float):
                raise ValueError('Finite built-in numbers required, not bool/string')
            value=float(value)
            if not math.isfinite(value):
                raise ValueError('Finite values required')
            if value<0 or (value==0 and key not in ['tip_load_n','uniform_load_n_m']):
                raise ValueError('Dimensions and declared limits positive; loads nonnegative')
            values[key]=value
        outputs=cantilever_values(*(values[key] for key in ['length_m','width_m','depth_m','youngs_modulus_pa','tip_load_n','uniform_load_n_m']))
        if outputs['slenderness']<values['declared_min_slenderness'] or outputs['deflection_ratio']>values['declared_max_deflection_ratio'] or outputs['tip_slope_rad']>values['declared_max_slope_rad']:
            raise ValueError('Outside caller-declared applicability envelope')
        result['outputs']=outputs
        result['output_units']=dict(UNITS)
        result['status']='SCREENING_COMPUTED'
    except (ValueError,OverflowError,ZeroDivisionError) as exc:
        result['reasons']=[str(exc)]
    return result
