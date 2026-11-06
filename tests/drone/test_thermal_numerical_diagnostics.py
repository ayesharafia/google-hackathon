"""Floating-point diagnostics; these checks do not establish physical accuracy."""

import math
from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from physimesh.drone.thermal import screen_thermal


def _oracle(C, T, Ta, Q, H, dt, precision):
    with localcontext() as ctx:
        ctx.prec = precision
        C, T, Ta, Q, H, dt = (Decimal.from_float(float(v)) for v in (C, T, Ta, Q, H, dt))
        equilibrium = Ta + Q / H
        end = equilibrium + (T - equilibrium) * (-H * dt / C).exp()
        return end, C * (end - T)


def _request(C, T, Ta, Q, H, dt):
    return {
        "evaluation": "lumped_thermal_screening",
        "mass_kg": C,
        "specific_heat_j_kg_k": 1.0,
        "initial_temperature_k": T,
        "lumped_biot_number": 0.05,
        "property_source": "diagnostic",
        "segments": [
            {"duration_s": dt, "ambient_temperature_k": Ta, "heat_input_w": Q, "conductance_w_k": H}
        ],
    }


def _assert_unqualified(result):
    assert result["evidence_level"] == "unverified"
    assert result["aircraft_status"] is None
    assert result["feasibility"] is None


def test_storage_cancellation_witness(record_property):
    C, T, Ta = 20630326.60223495, 616.3314368555151, 636.8048987945799
    Q, H, dt = 4282.472978229268, 1.0573382501356714, 0.00011144395875320127
    request = _request(C, T, Ta, Q, H, dt)
    original = deepcopy(request)
    result = screen_thermal(request)
    assert request == original
    assert result["status"] == "SCREENING_COMPUTED"
    _assert_unqualified(result)
    row = result["outputs"]["segments"][0]
    end = row["end_temperature_k"]
    storage = row["thermal_storage_change_j"]
    assert storage == C * (end - T)
    residual = row["energy_balance_residual_j"]
    assert residual == row["heat_input_j"] - storage - row["convective_exchange_j"]
    assert residual != 0.0
    assert result["outputs"]["total_energy_balance_residual_j"] == residual
    reference90 = _oracle(C, T, Ta, Q, H, dt, 90)
    reference120 = _oracle(C, T, Ta, Q, H, dt, 120)
    with localcontext() as ctx:
        ctx.prec = 120
        for a, b in zip(reference90, reference120):
            assert abs(a - b) <= abs(b) * Decimal("1e-75")
        error = abs(Decimal.from_float(storage) - reference120[1])
        # Returning a rounded temperature introduces storage error on C*ulp(T)'s
        # scale; eight allows preceding arithmetic too, for this witness only.
        envelope = 8 * Decimal.from_float(C) * Decimal.from_float(math.ulp(T))
        assert 0 < error <= envelope
        record_property("storage_absolute_error_j", float(error))
        record_property("storage_relative_error", float(error / abs(reference120[1])))


@pytest.mark.parametrize("C", [1.0, 10.0])
@pytest.mark.parametrize("duration", [500, 600, 700, 708, 709, 740, 745, 746, 750, 800])
def test_direct_binary64_decay_boundaries(C, duration):
    T, Ta, Q, H, dt = 1e300, 1e-100, 0.0, C, float(duration)
    request = _request(C, T, Ta, Q, H, dt)
    original = deepcopy(request)
    reference, _ = _oracle(C, T, Ta, Q, H, dt, 120)
    assert reference > 0
    result = screen_thermal(request)
    assert request == original
    _assert_unqualified(result)
    if duration <= 708:
        assert result["status"] == "SCREENING_COMPUTED"
        expected = float(reference)
        actual = result["outputs"]["final_temperature_k"]
        assert actual > 0
        # Numerical regression tolerance, never a physical acceptance threshold.
        assert abs(actual - expected) <= max(8 * math.ulp(expected), 2e-13 * expected)
    else:
        assert result["status"] == "MODEL_INAPPLICABLE"
        assert result["outputs"] == {}
        assert result["output_units"] == {}
