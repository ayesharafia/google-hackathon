import math
from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from physimesh.drone import dc_motor as m
from physimesh.drone.provenance import sha256_record

CHECKS = ("current", "terminal_voltage", "angular_speed", "shaft_torque")
LIMITS = tuple("maximum_" + s for s in (
    "current_a", "terminal_voltage_v", "angular_speed_rad_s", "shaft_torque_nm"))

def request():
    return {
        "evaluation": m.EVALUATION,
        "parameters": {"motor_constant_si": .1, "terminal_resistance_ohm": .2,
                       "zero_torque_current_a": .5, "parameter_source": "Synthetic",
                       "applicability_declaration": "constant_parameter_dc_equivalent_only"},
        "operating_point": {"angular_speed_rad_s": 300, "shaft_torque_nm": .15},
        "declared_limits": dict(zip(LIMITS, (10, 48, 500, 1)), limit_source="Synthetic"),
    }

@pytest.fixture
def motor_request():
    return request()

def evaluate(req):
    before = deepcopy(req)
    result = m.evaluate_dc_motor(req)
    assert req == before
    assert result["request_sha256"] == sha256_record(before)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["diagnostics_complete"] is True
    for key in ("physical_validation", "numerical_qualification"):
        assert result[key] == "NOT_ESTABLISHED"
    assert result["runtime_identity"] == "NOT_ESTABLISHED"
    assert result["aircraft_status"] is None and result["feasibility"] is None
    assert result["reasons"] == result["stages"] == result["transfers"] == []
    units = dict.fromkeys(("shaft_power_w", "electrical_power_w", "copper_loss_w",
                          "friction_equivalent_loss_w", "total_loss_w",
                          "power_balance_residual_w"), "W")
    units.update(current_a="A", back_emf_v="V", terminal_voltage_v="V",
                 efficiency="1", declared_limit_status="not_applicable",
                 limit_checks=dict.fromkeys(CHECKS, "not_applicable"))
    assert result["output_units"] == units
    assert set(result["outputs"]) == set(units)
    return result["outputs"]

def test_reference(motor_request):
    o = evaluate(motor_request)
    expected = {'current_a': 2, 'back_emf_v': 30, 'terminal_voltage_v': 30.4, 'shaft_power_w': 45, 'electrical_power_w': 60.8, 'copper_loss_w': 0.8, 'friction_equivalent_loss_w': 15, 'total_loss_w': 15.8, 'efficiency': 45 / 60.8}
    for key, value in expected.items():
        assert o[key] == pytest.approx(value)
    assert abs(o["power_balance_residual_w"]) < 1e-12
    assert o["declared_limit_status"] == "WITHIN_DECLARED_LIMITS"
    assert o["limit_checks"] == dict.fromkeys(CHECKS, True)

@pytest.mark.parametrize("index", range(4))
def test_inclusive_limits(motor_request, index):
    o = evaluate(motor_request)
    actual = (o["current_a"], o["terminal_voltage_v"], 300, .15)
    assert actual == pytest.approx((2, 30.4, 300, .15))
    motor_request["declared_limits"].update(zip(LIMITS, actual))
    assert evaluate(motor_request)["limit_checks"] == dict.fromkeys(CHECKS, True)
    motor_request["declared_limits"][LIMITS[index]] = math.nextafter(actual[index], 0)
    o = evaluate(motor_request)
    assert o["limit_checks"] == {key: j != index for j, key in enumerate(CHECKS)}
    assert o["declared_limit_status"] == "EXCEEDS_DECLARED_LIMITS"

@pytest.mark.parametrize("i0", [.5, 0])
def test_zero_torque(motor_request, i0):
    motor_request["parameters"]["zero_torque_current_a"] = i0
    motor_request["operating_point"]["shaft_torque_nm"] = 0
    o = evaluate(motor_request)
    assert o["shaft_power_w"] == 0 and o["current_a"] == i0
    assert o["back_emf_v"] == 30 and o["terminal_voltage_v"] == pytest.approx(30 + .2*i0)
    assert o["efficiency"] == (0 if i0 else None)
    assert o["copper_loss_w"] > 0 and o["friction_equivalent_loss_w"] > 0 if i0 else o["electrical_power_w"] == o["total_loss_w"] == 0

def test_ideal_and_decimal(motor_request):
    motor_request["parameters"].update(terminal_resistance_ohm=0, zero_torque_current_a=0)
    o = evaluate(motor_request)
    assert [o[k] for k in ("current_a", "terminal_voltage_v", "shaft_power_w", "electrical_power_w", "efficiency", "total_loss_w")] == pytest.approx([1.5, 30, 45, 45, 1, 0])
    motor_request["parameters"].update(motor_constant_si=.125, terminal_resistance_ohm=.25, zero_torque_current_a=.5)
    motor_request["operating_point"].update(angular_speed_rad_s=128, shaft_torque_nm=.25)
    with localcontext() as ctx:
        ctx.prec = 60
        k, r, i0, q, w = map(Decimal, (".125", ".25", ".5", ".25", "128"))
        i = q/k+i0
        e = k*w
        v = e+i*r
        p = v*i
        s = q*w
        c = i*i*r
        f = e*i0
        expected = {'current_a': i, 'back_emf_v': e, 'terminal_voltage_v': v, 'electrical_power_w': p, 'shaft_power_w': s, 'copper_loss_w': c, 'friction_equivalent_loss_w': f, 'total_loss_w': c + f, 'power_balance_residual_w': p - s - c - f, 'efficiency': s / p}
    o = evaluate(motor_request)
    assert {key: o[key] for key in expected} == {key: float(value) for key, value in expected.items()}



def test_ideal_roundoff_preserves_reported_electrical_power(motor_request):
    motor_request["parameters"].update(
        motor_constant_si=.1,
        terminal_resistance_ohm=0,
        zero_torque_current_a=0,
    )
    motor_request["operating_point"].update(
        angular_speed_rad_s=300,
        shaft_torque_nm=.15,
    )
    o = evaluate(motor_request)
    assert o["efficiency"] == 1
    assert o["shaft_power_w"] == 45
    assert o["total_loss_w"] == 0
    assert o["current_a"] == .15 / .1
    assert o["terminal_voltage_v"] == .1 * 300
    assert o["electrical_power_w"] == (
        o["current_a"] * o["terminal_voltage_v"]
    )
    assert o["electrical_power_w"] != 45
    assert o["power_balance_residual_w"] == (
        o["electrical_power_w"]
        - (o["shaft_power_w"] + o["total_loss_w"])
    )
    assert abs(o["power_balance_residual_w"]) / 45 <= 64 * math.ulp(1.0)


@pytest.mark.parametrize("path,value", [
    ("parameters.motor_constant_si", 0),
    ("parameters.motor_constant_si", True),
    ("parameters.motor_constant_si", math.nan),
    ("parameters.motor_constant_si", 1e-320),
    ("parameters.terminal_resistance_ohm", -1),
    ("parameters.zero_torque_current_a", -1),
    ("operating_point.angular_speed_rad_s", 0),
    ("operating_point.angular_speed_rad_s", -1),
    ("operating_point.shaft_torque_nm", -1),
    ("parameters.applicability_declaration", "BLDC"),
    ("declared_limits.maximum_current_a", 0),
    ("parameters.parameter_source", "   "),
    ("extra", 1),
])
def test_invalid_request_never_computes_or_hashes(monkeypatch, path, value):
    data = request()
    target = data
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    before, calls = deepcopy(data), []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("forbidden")
    monkeypatch.setattr(m, "_compute", forbidden)
    monkeypatch.setattr(m, "sha256_record", forbidden)
    result = m.evaluate_dc_motor(data)
    assert result["status"] == "GRAPH_INVALID"
    assert result["outputs"] == {}
    assert "request_sha256" not in result
    assert result["stages"] == result["transfers"] == []
    assert calls == [] and data == before


@pytest.mark.parametrize("exc", [RuntimeError, AssertionError, LookupError])
def test_runtime_failure_is_generic_and_atomic(monkeypatch, exc):
    data, private = request(), "private_exception_detail"
    before = deepcopy(data)
    def empty_failure(*args, **kwargs):
        raise RuntimeError()
    monkeypatch.setattr(m, "_compute", empty_failure)
    generic = m.evaluate_dc_motor(data)
    def private_failure(*args, **kwargs):
        raise exc(private)
    monkeypatch.setattr(m, "_compute", private_failure)
    result = m.evaluate_dc_motor(data)
    assert result == generic
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == sha256_record(data)
    assert result["outputs"] == {} and result["reasons"]
    assert private not in str(result) and data == before


def test_keyboard_interrupt_propagates(monkeypatch):
    data = request()
    before = deepcopy(data)
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr(m, "_compute", interrupt)
    with pytest.raises(KeyboardInterrupt):
        m.evaluate_dc_motor(data)
    assert data == before


@pytest.mark.parametrize("changes", [
    {"zero_torque_current_a": 1e-20},
    {"terminal_resistance_ohm": 1e-20},
    {"motor_constant_si": 1e308},
])
def test_numeric_failure_is_atomic(changes):
    data = request()
    data["parameters"].update(changes)
    if changes.get("motor_constant_si") == 1e308:
        data["operating_point"]["angular_speed_rad_s"] = 1e308
    before = deepcopy(data)
    result = m.evaluate_dc_motor(data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] == sha256_record(data)
    assert result["outputs"] == {} and data == before


def test_poison_dict_rejected_without_calls(monkeypatch):
    class Poison(dict):
        def __deepcopy__(self, memo):
            raise AssertionError("private_deepcopy")
    data, calls = Poison(request()), []
    before = deepcopy(dict(data))
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("forbidden")
    monkeypatch.setattr(m, "_compute", forbidden)
    monkeypatch.setattr(m, "sha256_record", forbidden)
    result = m.evaluate_dc_motor(data)
    assert result["status"] == "GRAPH_INVALID" and result["outputs"] == {}
    assert calls == [] and data == before


@pytest.mark.parametrize("k", [0.125, 0.25, 0.5])
@pytest.mark.parametrize("R", [0, 0.125, 0.25])
@pytest.mark.parametrize("I0", [0, 0.25])
@pytest.mark.parametrize("Q", [0, 0.125, 0.5])
@pytest.mark.parametrize("omega", [64, 128])
def test_dc_motor_exact_decimal_outputs(k, R, I0, Q, omega):
    req = deepcopy(request())
    req["parameters"].update(
        motor_constant_si=k,
        terminal_resistance_ohm=R,
        zero_torque_current_a=I0,
    )
    req["operating_point"].update(
        angular_speed_rad_s=omega, shaft_torque_nm=Q,
    )
    with localcontext() as ctx:
        ctx.prec = 70
        kd, rd, i0d, qd, wd = (Decimal(str(x)) for x in (k, R, I0, Q, omega))
        current = qd / kd + i0d
        emf = kd * wd
        voltage = emf + current * rd
        shaft = qd * wd
        copper = current * current * rd
        friction = emf * i0d
        loss = copper + friction
        expected = {
            'current_a': current,
            'back_emf_v': emf,
            'terminal_voltage_v': voltage,
            'shaft_power_w': shaft,
            'electrical_power_w': voltage * current,
            'copper_loss_w': copper,
            'friction_equivalent_loss_w': friction,
            'total_loss_w': loss,
        }
        eta = shaft / (shaft + loss) if shaft + loss else None
        actual = evaluate(req)
        for name, value in expected.items():
            assert actual[name] == float(value), name
        assert actual["efficiency"] == (float(eta) if eta is not None else None)
        assert actual["power_balance_residual_w"] == 0


class _PoisonDict(dict):
    def __deepcopy__(self, memo):
        raise AssertionError("poison deepcopy")


def _assert_empty_failure(result, code):
    assert result["status"] == code
    assert result["outputs"] == result["output_units"] == {}
    assert result["stages"] == result["transfers"] == []


@pytest.mark.parametrize("shape", [
    "none", "list", "unknownroot", "parameter_source2001",
    "deepnestedunknown11", "oversizeunknownlist257", "poison",
])
def test_invalid_graph_precedes_compute_and_hash(monkeypatch, shape):
    req = request()
    if shape == "none":
        req = None
    elif shape == "list":
        req = []
    elif shape == "unknownroot":
        req["extra_unknown"] = True
    elif shape == "parameter_source2001":
        req["parameters"]["parameter_source"] = "x" * 2001
    elif shape == "deepnestedunknown11":
        value = {}
        for _ in range(11):
            value = {"nested": value}
        req["extra_unknown"] = value
    elif shape == "oversizeunknownlist257":
        req["extra_unknown"] = [0] * 257
    else:
        req["extra_unknown"] = {"nested": _PoisonDict()}
    calls = []
    def forbidden(name):
        def fail(*args, **kwargs):
            calls.append(name)
            raise AssertionError(name)
        return fail
    monkeypatch.setattr(m, "_compute", forbidden("_compute"))
    monkeypatch.setattr(m, "sha256_record", forbidden("sha256_record"))
    result = m.evaluate_dc_motor(req)
    _assert_empty_failure(result, "GRAPH_INVALID")
    assert "request_sha256" not in result and calls == []


def test_units_failure_is_sanitized(monkeypatch):
    req, calls, actual_compute = request(), [], m._compute
    def compute(*args, **kwargs):
        result = actual_compute(*args, **kwargs)
        calls.append("computed")
        return result
    def fail_units(*args, **kwargs):
        assert calls == ["computed"]
        raise RuntimeError("private-unit-detail")
    monkeypatch.setattr(m, "_compute", compute)
    monkeypatch.setattr(m, "_units", fail_units)
    result = m.evaluate_dc_motor(req)
    _assert_empty_failure(result, "EXECUTION_FAILED")
    assert calls == ["computed"] and result["request_sha256"] == sha256_record(req)
    assert result["reasons"] == ["DC motor execution failed."]


def test_outputs_do_not_alias_request_or_later_results():
    req = request()
    original_request = deepcopy(req)
    result = m.evaluate_dc_motor(req)
    original_outputs = deepcopy(result["outputs"])
    result["outputs"]["limit_checks"]["current"] = False
    result["outputs"]["current_a"] = -1
    assert m.evaluate_dc_motor(req)["outputs"] == original_outputs
    assert req == original_request
