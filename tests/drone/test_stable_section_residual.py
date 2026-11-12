"""Private numerical/contract checks, never physical qualification."""

import hashlib
import json
import math
import struct
import sys
from copy import deepcopy
from fractions import Fraction

import mpmath as mp
import pytest

from physimesh.drone import section_load as load
from physimesh.drone import stable_section_residual as residual


def residual_request():
    return {"evaluation": residual.EVALUATION, "numerical_policy": deepcopy(residual._POLICY),
            "polar": {"airfoil_id": "invented", "source": "synthetic fixture; no dataset",
                      "source_kind": "synthetic", "uncertainty_status": "unknown",
                      "sampled_mach_number": 0.1, "declared_mach_interval": [0, 0.9],
                      "reynolds_tables": [{"reynolds_number": re, "rows": [
                          {"alpha_rad": alpha, "cl": 4, "cd": 0.1} for alpha in (-1.5, 0.0, 1.5)]}
                          for re in (1000.0, 10000000.0)]},
            "section": {"imposed_axial_velocity_m_s": 5, "imposed_tangential_velocity_m_s": 20,
                        "psi_rad": 0.6, "tip_radius_m": 0.8, "radius_m": 0.4,
                        "pitch_rad": 0.5, "chord_m": 0.1, "density_kg_m3": 1.2,
                        "dynamic_viscosity_pa_s": 1.8e-5, "speed_of_sound_m_s": 343, "blade_count": 2}}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def reseal(value):
    value["evaluation_sha256"] = digest({key: item for key, item in value.items() if key != "evaluation_sha256"})


def test_actual_child_native_hash_units_and_ownership():
    request = residual_request()
    before = deepcopy(request)
    result = residual.evaluate_stable_section_residual(request)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["load_result_count"] == result["lookup_result_count"] == 1
    output = result["outputs"]
    assert output["actual_load_result"] == load.evaluate_section_load(output["actual_load_request"])
    assert result["request_sha256"] == digest(request)
    assert result["evaluation_sha256"] == digest({k: v for k, v in result.items() if k != "evaluation_sha256"})
    assert request == before
    assert set(output["closure"]) == set(residual._CLOSURE_UNITS)
    assert set(output["factor_representation"]) == set(residual._FACTOR_UNITS)
    assert result["output_units"]["factor_representation"]["tip_rounding_effect_bound_m2_s"] == "m^2/s"
    request["section"]["imposed_axial_velocity_m_s"] = 5.0
    assert residual.evaluate_stable_section_residual(request)["request_sha256"] != result["request_sha256"]


@pytest.mark.parametrize("policy", [None, {}, {"id": "other", "f_min": 2**-20, "f_max": 512},
    {"id": "stable_deficit_binary64_v1", "f_min": 2**-20, "f_max": 512.0},
    {"id": "stable_deficit_binary64_v1", "f_min": True, "f_max": 512},
    {"id": "stable_deficit_binary64_v1", "f_min": 2**-20, "f_max": 512, "extra": 0}])
def test_policy_exact_before_calls(policy, monkeypatch):
    request = residual_request()
    request["numerical_policy"] = policy
    monkeypatch.setattr(load, "evaluate_section_load", lambda _: pytest.fail("unexpected child"))
    result = residual.evaluate_stable_section_residual(request)
    assert result["status"] == "MODEL_INAPPLICABLE" and result["load_result_count"] == 0
    assert result["request_sha256"] is result["evaluation_sha256"] is None


def test_policy_refusal_before_child_and_ood_nulls(monkeypatch):
    request = residual_request()
    request["section"]["radius_m"] = 1e-4
    with monkeypatch.context() as patch:
        patch.setattr(load, "evaluate_section_load", lambda _: pytest.fail("unexpected child"))
        result = residual.evaluate_stable_section_residual(request)
    assert result["status"] == "NUMERICAL_POLICY_REFUSED"
    assert result["reasons"] == ["F_OUTSIDE_NUMERICAL_POLICY"] and result["load_result_count"] == 0
    assert result["outputs"] == result["output_units"] == {}
    assert result["request_sha256"] == digest(request)
    request = residual_request()
    request["polar"].update(sampled_mach_number=0, declared_mach_interval=[0, 0])
    result = residual.evaluate_stable_section_residual(request)
    assert result["load_result_count"] == 1
    for key in ("closure", "factor_representation", "residual_m2_s"):
        assert result["outputs"][key] is None and result["output_units"][key] == "not_applicable"


def test_failed_guard_and_post_child_failure_counts(monkeypatch):
    original = load.evaluate_section_load

    def forged(request):
        result = original(request)
        result["lookup_result_count"] = True
        reseal(result)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(load, "evaluate_section_load", forged)
        result = residual.evaluate_stable_section_residual(residual_request())
    assert result["reasons"] == ["LOAD_BOUNDARY_FAILED"] and result["load_result_count"] == 0
    assert result["outputs"] == {}
    monkeypatch.setattr(residual, "_closure", lambda *args: (_ for _ in ()).throw(ArithmeticError("private")))
    result = residual.evaluate_stable_section_residual(residual_request())
    assert result["status"] == "EXECUTION_FAILED" and result["load_result_count"] == 1
    assert result["outputs"] == result["output_units"] == {}


@pytest.mark.parametrize("f", [2**-20, math.nextafter(2**-20, math.inf),
                              math.nextafter(512.0, 0), 512.0])
def test_representation_domain_endpoints(f):
    factor, gamma = residual._representation(f, 1.0)
    assert factor["f"] == f and gamma > 0 and factor["deficit"] >= sys.float_info.min


@pytest.mark.parametrize("f", [math.nextafter(2**-20, 0), math.nextafter(512.0, math.inf)])
def test_nextafter_outside_domain(f):
    with pytest.raises(ValueError):
        residual._representation(f, 1.0)


def test_rounded_one_retains_positive_deficit_and_correction():
    for f in (38.0, 110.557, 512.0):
        factor, gamma = residual._representation(f, 1.0)
        assert factor["factor_rounded"] == 1.0 and factor["deficit"] > 0
        assert factor["representation_state"] == "ROUNDED_ONE_WITH_POSITIVE_DEFICIT"
        assert factor["correction_m2_s"] > 0 and factor["correction_rounds_away"] is (gamma == 1.0)


def factor_transition():
    """Find adjacent binary64 f values at the NEW scalar rounding transition."""
    lo = struct.unpack(">Q", struct.pack(">d", 36.0))[0]
    hi = struct.unpack(">Q", struct.pack(">d", 40.0))[0]
    while hi - lo > 1:
        mid = (lo + hi) // 2
        value = struct.unpack(">d", struct.pack(">Q", mid))[0]
        rounded = 1.0 - (2.0 / math.pi) * math.asin(math.exp(-value))
        if rounded == 1.0:
            hi = mid
        else:
            lo = mid
    return tuple(struct.unpack(">d", struct.pack(">Q", bits))[0] for bits in (lo, hi))


def reference_values():
    values = [2**-20 * (512 / (2**-20)) ** (i / 99) for i in range(100)]
    values[0], values[-1] = 2**-20, 512.0
    values += [math.nextafter(2**-20, math.inf), math.nextafter(512.0, 0), 110.557]
    values += [math.nextafter(f, direction) for f in (36.0, 37.0, 38.0) for direction in (0, math.inf)]
    values += [36.29755781272286, 36.297557812722864, *factor_transition()]
    return values


def reference_summary(digits):
    """Observed relative differences at fixed emitted K=1; no libm error certificate."""
    worst = {key: (mp.mpf(0), None) for key in ("deficit", "gamma", "residual")}
    values = reference_values()
    with mp.workdps(digits):
        for f in values:
            factor, gamma = residual._representation(f, 1.0)
            exact_deficit = 2 / mp.pi * mp.asin(mp.exp(-mp.mpf(f)))
            exact_gamma = 1 - exact_deficit
            # Separate prescribed emitted lift, evaluated independently in high precision.
            emitted_residual = math.fsum((gamma, -0.125))
            exact_residual = exact_gamma - mp.mpf("0.125")
            errors = {"deficit": abs(mp.mpf(factor["deficit"]) / exact_deficit - 1),
                      "gamma": abs(mp.mpf(gamma) / exact_gamma - 1),
                      "residual": abs((mp.mpf(emitted_residual) - exact_residual) / exact_residual)}
            for key, error in errors.items():
                if error > worst[key][0]:
                    worst[key] = error, f
            assert mp.mpf(factor["tip_rounding_effect_bound_m2_s"]) >= exact_deficit
        return {"digits": digits, "cases": len(values),
                "max_relative_errors": {key: {"observed": mp.nstr(error, 40), "f": f}
                                        for key, (error, f) in worst.items()},
                "old_transition": [36.29755781272286, 36.297557812722864],
                "new_transition": list(factor_transition()),
                "scope": "Fixed emitted K=1 and prescribed lift=.125; observed differences, not total source-geometry error."}


@pytest.mark.parametrize("digits", [80, 120])
def test_independent_reference_100_cases_and_transitions(digits):
    stats = reference_summary(digits)
    assert float(stats["max_relative_errors"]["deficit"]["observed"]) < 1e-12
    assert float(stats["max_relative_errors"]["gamma"]["observed"]) < 1e-9
    old_lo, old_hi = stats["old_transition"]
    assert math.nextafter(old_lo, math.inf) == old_hi
    assert (2 / math.pi) * math.acos(math.exp(-old_lo)) < 1
    assert (2 / math.pi) * math.acos(math.exp(-old_hi)) == 1
    new_lo, new_hi = stats["new_transition"]
    assert math.nextafter(new_lo, math.inf) == new_hi
    assert residual._representation(new_lo, 1.0)[0]["factor_rounded"] < 1
    assert residual._representation(new_hi, 1.0)[0]["factor_rounded"] == 1


@pytest.mark.parametrize("digits", [80, 120])
def test_exact_outward_bounds_k_extremes_and_underflow(digits):
    with mp.workdps(digits):
        for f in (2**-20, 0.5, 1.0, 37.0, 110.557, 512.0):
            for k in (sys.float_info.min, 1e-160, 1e-100, 1.0, 1e300):
                bound = residual._effect_bound(f, k)
                exact_product = Fraction.from_float(k)
                if f >= 1:
                    exact_product /= 2**math.floor(f)
                assert Fraction.from_float(bound) >= exact_product
                exact_deficit = 2 / mp.pi * mp.asin(mp.exp(-mp.mpf(f)))
                assert mp.mpf(bound) >= mp.mpf(k) * exact_deficit
                correction = k * float(exact_deficit)
                if correction < sys.float_info.min:
                    with pytest.raises(ValueError):
                        residual._representation(f, k)
                else:
                    factor, gamma = residual._representation(f, k)
                    assert factor["correction_m2_s"] >= sys.float_info.min and gamma >= sys.float_info.min
        assert 0 < residual._effect_bound(512.0, 1e-160) < sys.float_info.min
        assert residual._effect_bound(512.0, sys.float_info.min) == math.nextafter(0.0, math.inf)
    with pytest.raises(ValueError):
        residual._effect_bound(0.5, sys.float_info.max)


def oversized_value(case, *, node_limit, depth_limit):
    """Small allocated graphs; repeated references still count at every JSON occurrence."""
    if case == "nodes":
        return [[None] * 256] * (node_limit // 257 + 1)
    if case == "depth":
        value = None
        for _ in range(depth_limit):
            value = [value]
        return value
    if case == "container":
        return [None] * 257
    if case == "string":
        return "x" * 2001
    if case == "integer":
        return 1 << 1023
    if case == "utf8":
        return "\ud800"
    if case == "circular":
        value = []
        value.append(value)
        return value
    raise AssertionError(case)


@pytest.mark.parametrize("case", ["nodes", "depth", "container", "string", "integer", "utf8", "circular", "bytes"])
def test_input_bound_before_untrusted_copy_hash_model(case, monkeypatch):
    request = residual_request()
    if case == "bytes":
        # Within node/string/container/depth limits, >1MiB compact UTF8 escaped data.
        request["oversized"] = ["\x00" * 2000] * 88
    else:
        request["oversized"] = oversized_value(case, node_limit=32768, depth_limit=16)
    original_copy, copied = residual.deepcopy, []

    def copying(value, *args, **kwargs):
        if value is request:
            copied.append(None)
            pytest.fail("untrusted request copied before native rejection")
        return original_copy(value, *args, **kwargs)  # Trusted refusal metadata only.

    monkeypatch.setattr(residual, "deepcopy", copying)
    monkeypatch.setattr(residual, "sha256_record", lambda _: pytest.fail("unexpected request hash"))
    monkeypatch.setattr(load, "evaluate_section_load", lambda _: pytest.fail("unexpected model"))
    result = residual.evaluate_stable_section_residual(request)
    assert result["status"] == "MODEL_INAPPLICABLE" and not copied
    assert result["load_result_count"] == 0 and result["outputs"] == result["output_units"] == {}


@pytest.mark.parametrize("failure", ["exception", "baseexception", "hash", "output_bound"])
def test_residual_failure_export_and_exception_contract(failure, monkeypatch):
    request = residual_request()
    if failure in ("exception", "baseexception"):
        def broken(_):
            if failure == "baseexception":
                raise KeyboardInterrupt("private interrupt")
            raise RuntimeError("private child detail")
        monkeypatch.setattr(load, "evaluate_section_load", broken)
        if failure == "baseexception":
            with pytest.raises(KeyboardInterrupt):
                residual.evaluate_stable_section_residual(request)
            return
    elif failure == "hash":
        original = residual.sha256_record

        def hashing(value):
            if "load_result_count" in value:
                raise RuntimeError("private export hash detail")
            return original(value)
        monkeypatch.setattr(residual, "sha256_record", hashing)
    else:
        original = residual._closure

        def too_large(*args):
            closure, factor, value = original(*args)
            factor["extra"] = "x" * 2001
            return closure, factor, value
        monkeypatch.setattr(residual, "_closure", too_large)
    result = residual.evaluate_stable_section_residual(request)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["load_result_count"] == (0 if failure == "exception" else 1)
    assert result["outputs"] == result["output_units"] == {}
    assert "private" not in json.dumps(result)
    if failure == "hash":
        assert result["request_sha256"] is result["evaluation_sha256"] is None
