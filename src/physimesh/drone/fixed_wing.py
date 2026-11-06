"""Supplied-coefficient screening; no numerical or flight-validity guarantee."""
import math
import sys
from fractions import Fraction

_MODEL = 'fixed_wing_supplied_coefficient_screening_v1'
_NUMBERS = (
    'density_kg_m3', 'airspeed_m_s', 'wing_area_m2', 'span_m',
    'characteristic_length_m', 'dynamic_viscosity_pa_s',
    'speed_of_sound_m_s', 'lift_coefficient',
    'zero_lift_drag_coefficient', 'span_efficiency',
)
_FIELDS = frozenset(_NUMBERS) | {
    'configuration', 'evaluation', 'coefficient_source', 'coefficient_envelope',
}
_BOUNDS = frozenset({
    'mach_min', 'mach_max', 'reynolds_min', 'reynolds_max',
    'lift_coefficient_min', 'lift_coefficient_max',
})
_NAMES = (
    'dynamic_pressure_pa', 'aspect_ratio', 'induced_drag_coefficient',
    'drag_coefficient', 'lift_n', 'drag_n', 'drag_power_w',
    'reynolds_number', 'mach_number',
)
_UNITS = ('Pa', '1', '1', '1', 'N', 'N', 'W', '1', '1')


def _number(value):
    if type(value) is int:
        if value.bit_length() > 1024:
            raise ValueError('integer too large')
    elif type(value) is not float or not math.isfinite(value):
        raise ValueError('finite number required')
    try:
        result = float(value)
    except OverflowError:
        raise ValueError('number out of range') from None
    if not math.isfinite(result):
        raise ValueError('number out of range')
    return result


def _arithmetic(operator, a, b):
    if operator == '*':
        result = a * b
    elif operator == '/':
        if b == 0:
            raise ValueError('zero denominator')
        result = a / b
    else:
        result = a + b
    if not math.isfinite(result):
        raise ValueError('arithmetic overflow')
    if abs(result) < sys.float_info.min:
        x, y = Fraction(a), Fraction(b)
        exact = x * y if operator == '*' else x / y if operator == '/' else x + y
        if Fraction(result) != exact:
            raise ValueError('arithmetic underflow')
    return result


def _sources():
    return {
        'urls': [
            'https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/induced-drag-coefficient/',
            'https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/modern-drag-equation/',
        ],
        'pdf_reference': 'PDF A section 6.1',
        'verification': 'Reference links do not imply NASA or PDF-author validation of this implementation.',
    }


def screen_fixed_wing(request):
    """Return an unverified screening result without modifying the request."""
    result = {
        'status': 'MODEL_INAPPLICABLE', 'reasons': [],
        'outputs': {}, 'output_units': {}, 'model_id': _MODEL,
        'evidence_level': 'unverified', 'aircraft_status': None,
        'feasibility': None,
    }

    def refuse(reason, status='MODEL_INAPPLICABLE'):
        result['status'] = status
        result['reasons'] = [reason]
        return result

    if type(request) is not dict:
        return refuse('INVALID_REQUEST')
    if any(type(key) is not str for key in request) or set(request) != _FIELDS:
        return refuse('INVALID_REQUEST_KEYS')
    if type(request['configuration']) is not str or request['configuration'] != 'fixed_wing':
        return refuse('UNKNOWN_CONFIGURATION')
    evaluation = request['evaluation']
    if type(evaluation) is not str or not evaluation.strip():
        return refuse('INVALID_EVALUATION')
    if evaluation != 'fixed_wing_aerodynamic_screening':
        return refuse('UNSUPPORTED_EVALUATION', 'SOLVER_UNSUPPORTED')
    source = request['coefficient_source']
    if type(source) is not str or not 1 <= len(source) <= 2000 or not source.strip():
        return refuse('INVALID_COEFFICIENT_SOURCE')
    envelope = request['coefficient_envelope']
    if type(envelope) is not dict:
        return refuse('INVALID_COEFFICIENT_ENVELOPE')
    if any(type(key) is not str for key in envelope) or set(envelope) != _BOUNDS:
        return refuse('INVALID_COEFFICIENT_ENVELOPE')
    try:
        values = {key: _number(request[key]) for key in _NUMBERS}
        bounds = {key: _number(envelope[key]) for key in _BOUNDS}
        if any(values[key] <= 0 for key in _NUMBERS[:7]):
            raise ValueError('positive physical inputs required')
        rho, speed, area, span, length, viscosity, sound = (values[key] for key in _NUMBERS[:7])
        cl, cd0, efficiency = (values[key] for key in _NUMBERS[7:])
        if cd0 < 0 or not 0 < efficiency <= 1:
            raise ValueError('invalid drag coefficient or efficiency')
        if bounds['mach_min'] < 0 or bounds['reynolds_min'] <= 0:
            raise ValueError('invalid envelope bounds')
        for name in ('mach', 'reynolds', 'lift_coefficient'):
            if bounds[name + '_max'] < bounds[name + '_min']:
                raise ValueError('reversed envelope')

        def mul(a, b):
            return _arithmetic('*', a, b)

        def div(a, b):
            return _arithmetic('/', a, b)

        reynolds = div(mul(mul(rho, speed), length), viscosity)
        mach = div(speed, sound)
        for name, actual in (('mach', mach), ('reynolds', reynolds), ('lift_coefficient', cl)):
            if not bounds[name + '_min'] <= actual <= bounds[name + '_max']:
                return refuse('COEFFICIENT_OUTSIDE_DECLARED_ENVELOPE')
        q = div(mul(rho, mul(speed, speed)), 2.0)
        aspect_ratio = div(mul(span, span), area)
        induced = div(mul(cl, cl), mul(mul(math.pi, efficiency), aspect_ratio))
        drag_coefficient = _arithmetic('+', cd0, induced)
        lift = mul(mul(q, area), cl)
        drag = mul(mul(q, area), drag_coefficient)
        power = mul(drag, speed)
        if q <= 0 or aspect_ratio <= 0 or reynolds <= 0 or mach <= 0:
            raise ValueError('invalid derived positive quantity')
        if min(induced, drag_coefficient, drag, power) < 0:
            raise ValueError('negative drag quantity')
    except (ArithmeticError, ValueError, TypeError):
        return refuse('INVALID_NUMERIC_INPUT_OR_ARITHMETIC')
    result.update({
        'status': 'SCREENING_COMPUTED',
        'outputs': dict(zip(_NAMES, (q, aspect_ratio, induced, drag_coefficient, lift, drag, power, reynolds, mach))),
        'output_units': dict(zip(_NAMES, _UNITS)),
        'coefficient_source': source,
        'coefficient_envelope': dict(envelope),
        'source_metadata': _sources(),
        'limitations': [
            'Supplied coefficients and declared envelope are unverified; inclusion does not establish applicability.',
            'Classical parabolic polar and lifting-line model restricted to planar wings with supplied span efficiency.',
            'No stall, critical-Mach, trim, propulsion, aeroelastic, structural, transition, or installed-aircraft verification.',
            'Drag power is aerodynamic D times V, not shaft or electrical power.',
            'No environmental or geometry inference; no weight equivalence, payload, climb rate, or propulsion-efficiency inference.',
            'No numerical-accuracy or flight-validity guarantees.',
        ],
    })
    return result
