"""Constant-property lumped thermal screening, not aircraft validation."""
import math
import sys

MODEL_ID = 'thermal_lumped_constant_segments_v1'
LIMITATIONS = [
    'Properties, heat input, conductance, source note and Biot number are caller declarations, unverified.',
    'Uniform temperature and constant properties within each segment are assumed.',
    'No radiation, phase change, internal gradients, hotspots, chemistry or thermal runaway model.',
    'No failure threshold, aircraft safety, feasibility or validation assessment.',
    'Numerical screening refuses subnormal derived intermediates and underflow; no scaled extended-range solver is implemented.',
    'Energy residual is an arithmetic conservation check, not independent physical validation.',
    'Biot declaration within [0,0.1] is a screening gate, not physical verification; the conventional criterion is Bi < 0.1.',
]
FIELDS = {'evaluation','mass_kg','specific_heat_j_kg_k','initial_temperature_k','lumped_biot_number','property_source','segments'}
SEGMENT_FIELDS = {'duration_s','ambient_temperature_k','heat_input_w','conductance_w_k'}


def _number(value):
    if type(value) not in (int,float):
        raise ValueError('Expected a finite built-in number, not bool or string')
    value=float(value)
    if not math.isfinite(value):
        raise ValueError('Nonfinite number')
    return value


def _finite(value):
    if not math.isfinite(value) or (value != 0 and abs(value) < sys.float_info.min):
        raise ValueError('Nonfinite derived value')
    return value


def screen_thermal(request):
    result = {
        'model_id':MODEL_ID,'status':'MODEL_INAPPLICABLE','evidence_level':'unverified',
        'aircraft_status':None,'feasibility':None,'outputs':{},'output_units':{},
        'limitations':list(LIMITATIONS),'reasons':[],
        'sources':[{'url':'https://ocw.nthu.edu.tw/upload/77/news/HTchap5.pdf',
                    'scope':'Lumped energy balance, time constant, Bi<0.1 and heat generation extension'}],
    }
    try:
        if type(request) is not dict or set(request)!=FIELDS:
            raise ValueError('Exact request fields required')
        if type(request['evaluation']) is not str or request['evaluation']!='lumped_thermal_screening':
            result['status']='SOLVER_UNSUPPORTED'
            raise ValueError('Unsupported evaluation')
        mass,cp,temperature,biot=map(_number,[request['mass_kg'],request['specific_heat_j_kg_k'],request['initial_temperature_k'],request['lumped_biot_number']])
        if min(mass,cp,temperature)<=0 or not 0<=biot<=0.1:
            raise ValueError('Positive mass, specific heat and absolute temperature; Biot in [0,0.1] required')
        source=request['property_source']
        if type(source) is not str or not source.strip() or len(source)>2000:
            raise ValueError('Nonblank property source up to 2000 characters required')
        capacity=checked_product(mass,cp)
        if capacity<=0:
            raise ValueError('Thermal capacity underflow')
        segments=request['segments']
        if type(segments) is not list or not 1<=len(segments)<=128:
            raise ValueError('Expected 1 to 128 segments')
        rows=[]
        elapsed=0.0
        maximum=temperature
        for index,segment in enumerate(segments):
            if type(segment) is not dict or set(segment)!=SEGMENT_FIELDS:
                raise ValueError('Exact segment fields required')
            duration,ambient,heat,conductance=map(_number,[segment['duration_s'],segment['ambient_temperature_k'],segment['heat_input_w'],segment['conductance_w_k']])
            if min(duration,ambient)<=0 or min(heat,conductance)<0:
                raise ValueError('Invalid segment bounds')
            end,input_j,stored,convective,residual=integrate_segment(capacity,temperature,ambient,heat,conductance,duration)
            new_elapsed=_finite(elapsed+duration)
            if new_elapsed<=elapsed:
                raise ValueError('Elapsed time resolution loss')
            elapsed=new_elapsed
            rows.append({'index':index,'duration_s':duration,'cumulative_elapsed_s':elapsed,
                'start_temperature_k':temperature,'end_temperature_k':end,'ambient_temperature_k':ambient,
                'heat_input_j':input_j,'thermal_storage_change_j':stored,'convective_exchange_j':convective,'energy_balance_residual_j':residual})
            temperature=end
            maximum=max(maximum,end)
        total_input=_finite(math.fsum(row['heat_input_j'] for row in rows))
        total_storage=_finite(math.fsum(row['thermal_storage_change_j'] for row in rows))
        total_convection=_finite(math.fsum(row['convective_exchange_j'] for row in rows))
        total_residual=_finite(total_input-total_storage-total_convection)
        result['outputs']={'segments':rows,'elapsed_s':elapsed,'final_temperature_k':temperature,'maximum_temperature_k':maximum,
            'total_heat_input_j':total_input,'total_convective_exchange_j':total_convection,'total_storage_change_j':total_storage,'total_energy_balance_residual_j':total_residual}
        result['output_units']={'segments':{'index':'1','duration_s':'s','cumulative_elapsed_s':'s','start_temperature_k':'K','end_temperature_k':'K','ambient_temperature_k':'K','heat_input_j':'J','thermal_storage_change_j':'J','convective_exchange_j':'J','energy_balance_residual_j':'J'},'elapsed_s':'s','final_temperature_k':'K','maximum_temperature_k':'K','total_heat_input_j':'J','total_convective_exchange_j':'J','total_storage_change_j':'J','total_energy_balance_residual_j':'J'}
        result['status']='SCREENING_COMPUTED'
    except (ValueError,OverflowError,ZeroDivisionError) as exc:
        result['outputs']={}
        result['output_units']={}
        result['reasons']=[str(exc)]
    return result


def integrate_segment(C, T, Ta, Q, H, dt):
    def finite(v):
        if not math.isfinite(v) or (v != 0 and abs(v) < sys.float_info.min):
            raise ValueError("Nonfinite intermediate")
        return v

    input_j = checked_product(Q, dt)
    if Q > 0.0 and input_j == 0.0:
        raise ValueError("Input energy underflow")
    if H == 0.0:
        delta = checked_quotient(input_j, C)
        convection_j = 0.0
        equilibrium = Q == 0.0
    else:
        hdt = checked_product(H, dt)
        x = checked_quotient(hdt, C)
        if x == 0.0:
            raise ValueError("Positive-H exponent underflow")
        om = -math.expm1(-x)
        phi = checked_quotient(om, x)
        if x < 1e-4:
            one_minus_phi = x * (0.5 + x * (-1.0 / 6.0 + x *
                (1.0 / 24.0 + x * (-1.0 / 120.0 + x / 720.0))))
        else:
            one_minus_phi = 1.0 - phi
        difference = checked_difference(T, Ta)
        net = checked_difference(Q, checked_product(H, difference))
        equilibrium = net == 0.0
        delta = checked_product(checked_quotient(checked_product(net, dt), C), phi)
        initial_loss = checked_product(checked_product(hdt, difference), phi)
        source_loss = checked_product(input_j, one_minus_phi)
        convection_j = finite(initial_loss + source_loss)

    if equilibrium:
        Tnext = T
    elif H == 0.0:
        Tnext = finite(T + delta)
    else:
        decay = finite(math.exp(-x))
        if decay == 0.0:
            raise ValueError("Exponential underflow; scaled decay product is unsupported")
        Tnext = finite(math.fsum([checked_product(T, decay), checked_product(Ta, om),
            checked_product(checked_quotient(input_j, C), phi)]))
    if Tnext <= 0.0:
        raise ValueError("Nonpositive temperature")
    if not equilibrium and (delta == 0.0 or Tnext == T):
        raise ValueError("Temperature resolution loss")
    storage_j = checked_product(C, checked_difference(Tnext, T))
    residual_j = finite(finite(input_j - storage_j) - convection_j)
    return Tnext, input_j, storage_j, convection_j, residual_j



def checked_product(a, b):
    if not (math.isfinite(a) and math.isfinite(b)):
        raise ValueError("Nonfinite operand")
    r = a * b
    if not math.isfinite(r) or (r != 0 and abs(r) < sys.float_info.min):
        raise ValueError("Overflow or subnormal product")
    if r == 0 and a != 0 and b != 0:
        raise ValueError("Product underflow")
    return r

def checked_difference(a, b):
    if not (math.isfinite(a) and math.isfinite(b)):
        raise ValueError("Nonfinite operand")
    r = a - b
    if not math.isfinite(r) or (r != 0 and abs(r) < sys.float_info.min):
        raise ValueError("Overflow or subnormal difference")
    if r == 0 and a != b:
        raise ValueError("Difference underflow")
    return r


def checked_quotient(a, b):
    value = a / b
    if not math.isfinite(value) or (value != 0 and abs(value) < sys.float_info.min) or (a != 0 and value == 0):
        raise ValueError("Quotient outside normal finite arithmetic")
    return value
