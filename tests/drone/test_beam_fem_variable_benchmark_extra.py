"""Independent tests for the new variable-beam MMS benchmark contract."""
import itertools
import json
import math
import sys

import pytest

from physimesh.drone.beam_fem_variable_benchmark import benchmark_variable_mms

BASE = {"length_m": 2.0, "E_pa": 70e9, "I_root_m4": 1e-6,
            "outer_fibre_m": 0.02, "deflection_scale_m": 0.001}
FAMILY = tuple(tuple(2.0 * i / n for i in range(n + 1)) for n in (4, 8, 16))
ROW_KEYS = {"elements", "max_element_length_m", "tip_deflection_m", "root_force_n", "root_moment_nm", "displacement_rms_error_m", "rotation_rms_error_rad", "stress_rms_error_pa", "displacement_order", "rotation_order", "stress_order", "normalized_linear_residual"}
TOP_KEYS = {"schema_version", "reference_kind", "physical_validation", "evidence_level", "aircraft_status", "feasibility", "rows", "ramp_tip_load_n_m", "exact_tip_deflection_m", "exact_root_force_n", "exact_root_moment_nm", "output_units", "limitations", "sources"}

def call(mesh_nodes=FAMILY, **changes):
    return benchmark_variable_mms(**(BASE | changes), mesh_nodes=mesh_nodes)

@pytest.fixture(scope="module")
def result():
    return call()

def test_exact_reference_fixture(result):
    for key, expected in {"ramp_tip_load_n_m": 157.5,
                              "exact_tip_deflection_m": 0.003,
                              "exact_root_force_n": -157.5,
                              "exact_root_moment_nm": -210.0}.items():
        assert result[key] == pytest.approx(expected, rel=1e-13, abs=1e-15)

def check_rows(result, family):
    assert type(result["rows"]) is list
    assert len(result["rows"]) == len(family)
    fields = (("displacement", "m", 0.001), ("rotation", "rad", 0.0005),
              ("stress", "pa", 70e9 * 0.02 * 0.001 / 4))
    for i, (row, nodes) in enumerate(zip(result["rows"], family)):
        assert set(row) == ROW_KEYS
        assert type(row["elements"]) is int
        assert row["elements"] == len(nodes) - 1
        h = max(b - a for a, b in itertools.pairwise(nodes))
        assert row["max_element_length_m"] == pytest.approx(h, rel=1e-14)
        assert row["normalized_linear_residual"] >= 0
        for field, unit, scale in fields:
            error_key, order_key = f"{field}_rms_error_{unit}", f"{field}_order"
            error = row[error_key]
            assert error >= 0
            expected = None
            if i:
                prev = result["rows"][i - 1]
                old_error, old_h = prev[error_key], prev["max_element_length_m"]
                if old_error > error > 64 * sys.float_info.epsilon * scale:
                    expected = ((math.log(old_error) - math.log(error)) /
                                (math.log(old_h) - math.log(h)))
            if expected is None:
                assert row[order_key] is None
            else:
                assert row[order_key] == pytest.approx(expected, rel=1e-11, abs=1e-12)

def test_uniform_hmax_and_manual_orders(result):
    check_rows(result, FAMILY)

def test_graded_family_uses_actual_hmax():
    family = ((0., 0.2, 0.7, 2.), (0., 0.25, 0.8, 1.4, 2.),
              (0., 0.2, 0.55, 0.9, 1.25, 1.6, 2.))
    check_rows(call(family), family)

def test_metadata_finite_json_and_determinism(result):
    assert set(result) == TOP_KEYS
    assert result["schema_version"] == "variable_beam_mms_refinement_v1"
    assert result["reference_kind"] == "manufactured_quartic_exact_linear_inertia"
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["evidence_level"] == "unverified"
    assert result["feasibility"] is result["aircraft_status"] is None
    for key in ("limitations", "sources"):
        assert type(result[key]) is list and result[key]
        assert all(type(item) is str and item for item in result[key])
    sources = " ".join(result["sources"]).lower()
    assert "colorado.edu" in sources and "osti.gov" in sources and "759450" in sources
    assert type(result["output_units"]) is dict
    assert ROW_KEYS <= result["output_units"].keys()
    assert all(type(unit) is str and unit for unit in result["output_units"].values())
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert call() == result


@pytest.mark.parametrize("mesh", [(), (FAMILY[0],), FAMILY * 3, None,
    ((0., 2.), (0., 2.)), ((0., 1., 2.), (0., 0.5, 2.)),
    ((0., 1., 2.), (0., 1., 1., 2.)), ((0., 1., 2.), (0., 1.5, 1., 2.)),
    ((0., 1., 2.), (0.1, 0.5, 1., 1.5, 2.)),
    ((0., 1., 2.), (0., 0.5, 1., 1.5, 2.1)),
    ((0., 1., 2.), (0., float("nan"), 2.)),
    (FAMILY[0], tuple(2. * i / 65 for i in range(66)))])
def test_malformed_mesh_family(mesh):
    with pytest.raises((TypeError, ValueError)):
        call(mesh)


@pytest.mark.parametrize("name", tuple(BASE))
@pytest.mark.parametrize("value", [0., -1., float("nan"), float("inf"),
                                         -float("inf"), True, "1", None, 1j])
def test_invalid_numeric(name, value):
    with pytest.raises((TypeError, ValueError)):
        call(**{name: value})


@pytest.mark.parametrize("value", [math.ulp(0.), sys.float_info.max])
def test_invalid_deflection_scale_extremes(value):
    with pytest.raises((TypeError, ValueError, OverflowError)):
        call(deflection_scale_m=value)
