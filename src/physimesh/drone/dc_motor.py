import math
import sys
from copy import deepcopy

from . import thermal as th
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = "constant_parameter_dc_motor_experimental"


def _preflight(request):
    _json(request, budget=4096)
    _require(type(request) is dict and set(request) == {
        "evaluation", "parameters", "operating_point", "declared_limits"
    })
    _require(type(request["evaluation"]) is str
             and request["evaluation"] == EVALUATION)
    specifications = (
        ("parameters", (
            ("motor_constant_si", True),
            ("terminal_resistance_ohm", False),
            ("zero_torque_current_a", False),
        ), ("parameter_source", "applicability_declaration")),
        ("operating_point", (
            ("angular_speed_rad_s", True),
            ("shaft_torque_nm", False),
        ), ()),
        ("declared_limits", (
            ("maximum_current_a", True),
            ("maximum_terminal_voltage_v", True),
            ("maximum_angular_speed_rad_s", True),
            ("maximum_shaft_torque_nm", True),
        ), ("limit_source",)),
    )
    for section_name, numeric_fields, other_fields in specifications:
        section = request[section_name]
        expected = {name for name, _ in numeric_fields} | set(other_fields)
        _require(type(section) is dict and set(section) == expected)
        for name, positive in numeric_fields:
            value = section[name]
            _require(type(value) in (int, float))
            _require(value == 0 or
                     sys.float_info.min <= abs(value) <= sys.float_info.max)
            value = _normal(value)
            _require(math.isfinite(value))
            _require(value > 0 if positive else value >= 0)
        for name in other_fields:
            value = section[name]
            _require(type(value) is str)
            if name == "applicability_declaration":
                _require(value == "constant_parameter_dc_equivalent_only")
            else:
                _require(bool(value.strip()) and len(value) <= 2000)
    return deepcopy(request)


def _power_sum(values):
    total = 0.0
    for value in values:
        _require(type(value) in (int, float))
        _require(value == 0 or
                 sys.float_info.min <= value <= sys.float_info.max)
        value = _normal(value)
        _require(math.isfinite(value) and value >= 0)
        newtotal = _normal(math.fsum((total, value)))
        _require(value == 0 or newtotal > total)
        _require(total == 0 or newtotal > value)
        total = newtotal
    return total


def _compute(snapshot):
    # MIT Drela: the source's inverse KQ corresponds to the reciprocal of SI k.
    parameters = snapshot["parameters"]
    operating_point = snapshot["operating_point"]
    declared = snapshot["declared_limits"]
    k = _normal(parameters["motor_constant_si"])
    R = _normal(parameters["terminal_resistance_ohm"])
    I0 = _normal(parameters["zero_torque_current_a"])
    omega = _normal(operating_point["angular_speed_rad_s"])
    Q = _normal(operating_point["shaft_torque_nm"])
    _require(k > 0 and R >= 0 and I0 >= 0 and omega >= 0 and Q >= 0)

    current = _power_sum([th.checked_quotient(Q, k), I0])
    back_emf = th.checked_product(k, omega)
    voltage = _power_sum([back_emf, th.checked_product(current, R)])
    shaft = th.checked_product(Q, omega)
    electrical = th.checked_product(voltage, current)
    copper = (
        0.0 if R == 0
        else th.checked_product(th.checked_product(current, current), R)
    )
    friction = th.checked_product(back_emf, I0)
    losses = _power_sum([copper, friction])
    accounted = _power_sum([shaft, losses])
    residual = th.checked_difference(electrical, accounted)
    norm = max(electrical, accounted)
    if norm > 0:
        _require(
            abs(th.checked_quotient(residual, norm))
            <= th.checked_product(64, sys.float_info.epsilon)
        )
    else:
        _require(residual == 0)

    efficiency = (
        th.checked_quotient(shaft, accounted) if accounted > 0 else None
    )
    if efficiency is None:
        _require(shaft == 0 and losses == 0)
    else:
        _require(0 <= efficiency <= 1)

    checks = {}
    for name, actual, key in (
        ("current", current, "maximum_current_a"),
        ("terminal_voltage", voltage, "maximum_terminal_voltage_v"),
        ("angular_speed", omega, "maximum_angular_speed_rad_s"),
        ("shaft_torque", Q, "maximum_shaft_torque_nm"),
    ):
        maximum = _normal(declared[key])
        _require(maximum >= 0)
        checks[name] = actual <= maximum

    return {
        "current_a": current,
        "back_emf_v": back_emf,
        "terminal_voltage_v": voltage,
        "shaft_power_w": shaft,
        "electrical_power_w": electrical,
        "copper_loss_w": copper,
        "friction_equivalent_loss_w": friction,
        "total_loss_w": losses,
        "power_balance_residual_w": residual,
        "efficiency": efficiency,
        "declared_limit_status": (
            "WITHIN_DECLARED_LIMITS" if all(checks.values())
            else "EXCEEDS_DECLARED_LIMITS"
        ),
        "limit_checks": checks,
    }


def _units():
    return {
        "current_a": "A",
        "back_emf_v": "V",
        "terminal_voltage_v": "V",
        "shaft_power_w": "W",
        "electrical_power_w": "W",
        "copper_loss_w": "W",
        "friction_equivalent_loss_w": "W",
        "total_loss_w": "W",
        "power_balance_residual_w": "W",
        "efficiency": "1",
        "declared_limit_status": "not_applicable",
        "limit_checks": {
            key: "not_applicable"
            for key in ("current", "terminal_voltage", "angular_speed", "shaft_torque")
        },
    }


def evaluate_dc_motor(request):
    result = {
        'evaluation': EVALUATION,
        'status': 'GRAPH_INVALID',
        'evidence_level': 'unverified',
        'physical_validation': 'NOT_ESTABLISHED',
        'numerical_qualification': 'NOT_ESTABLISHED',
        'runtime_identity': 'NOT_ESTABLISHED',
        'aircraft_status': None,
        'feasibility': None,
        'diagnostics_complete': False,
        'reasons': [],
        'outputs': {},
        'output_units': {},
        'stages': [],
        'transfers': [],
        'sources': [{
            'url': 'https://web.mit.edu/drela/Public/web/qprop/motor1_theory.pdf',
            'scope': 'Steady constant-parameter DC-equivalent equations',
        }],
        'limitations': [
            'Caller-declared constant R and zero-torque current; no speed or temperature correction.',
            'No BLDC phase conversion, ESC, battery, bus current, SOC or regeneration model.',
            'Declared limits are not continuous thermal ratings or aircraft feasibility.',
            'Sources identify equations, not measured or qualified parameters.',
        ],
    }
    try:
        snapshot = _preflight(request)
    except (ValueError, TypeError, OverflowError, UnicodeError,
            RecursionError, KeyError, ZeroDivisionError):
        result['reasons'] = ['Invalid DC motor request.']
        return deepcopy(result)
    try:
        result['request_sha256'] = sha256_record(snapshot)
        outputs = _compute(snapshot)
        units = _units()
        result.update(
            status='COMPUTED_EXPERIMENTAL',
            diagnostics_complete=True,
            outputs=outputs,
            output_units=units,
        )
    except Exception:  # noqa: BLE001
        result['status'] = 'EXECUTION_FAILED'
        result['reasons'] = ['DC motor execution failed.']
    return deepcopy(result)
