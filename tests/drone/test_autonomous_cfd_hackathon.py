"""Fail-closed smoke tests for hackathon CFD admission and grid verification."""
import pytest
from physimesh.drone.autonomous_cfd import (
    GeometryDecision, GridResult, select_physics,
    propose_mesh_levels, assess_grid_independence,
)


def eligible_geometry():
    return GeometryDecision("SUPPORTED", "a" * 64, "stationary_sphere", (), 1.0)


def sample_triplet(values=(0.46, 0.415, 0.40375), cells=(1000, 8000, 64000)):
    return [GridResult(name, n, value, True, True, True, str(i + 1).zfill(64))
            for i, (name, n, value) in enumerate(zip(
                ("coarse", "medium", "fine"), cells, values))]


def test_admissible_physics_and_mesh_levels():
    result = select_physics(eligible_geometry(), speed_m_s=1.0, diameter_m=2.0,
                            nu_m2_s=0.01, sound_speed_m_s=340.0)
    assert result["status"] == "SUPPORTED"
    levels = propose_mesh_levels(result, base_divisions=(8, 10, 12))
    assert [x["background_divisions"] for x in levels] == [
        [8, 10, 12], [16, 20, 24], [32, 40, 48]
    ]


def test_unqualified_airframe_and_compressible_cases_refused():
    airframe = GeometryDecision("UNSUPPORTED", "a" * 64, "airframe", ("NO_QUALIFIED_CFD_ADAPTER",))
    result = select_physics(airframe, speed_m_s=1, diameter_m=2,
                            nu_m2_s=.01, sound_speed_m_s=340)
    assert result["status"] == "UNSUPPORTED"
    assert "GEOMETRY_NOT_ELIGIBLE" in result["reasons"]
    with pytest.raises(ValueError):
        propose_mesh_levels(result, base_divisions=(8, 8, 8))
    result = select_physics(eligible_geometry(), speed_m_s=120, diameter_m=2,
                            nu_m2_s=.01, sound_speed_m_s=300)
    assert "COMPRESSIBLE_REGIME_NOT_SUPPORTED" in result["reasons"]


def test_order_two_convergence():
    result = assess_grid_independence(sample_triplet(), quantity="drag_coefficient", tolerance=.02)
    assert result["status"] == "GRID_INDEPENDENT"
    assert result["observed_order"] == pytest.approx(2)
    assert result["richardson_extrapolation"] == pytest.approx(.4)


def test_nonmonotonic_grid_is_not_accepted():
    result = assess_grid_independence(sample_triplet(values=(.42, .40, .41)), quantity="Cd")
    assert result["status"] == "NOT_GRID_INDEPENDENT"


def test_conservation_failure_is_not_accepted():
    samples = sample_triplet()
    samples[1] = GridResult("medium", 8000, .415, True, True, False, "2".zfill(64))
    result = assess_grid_independence(samples, quantity="Cd")
    assert result["status"] == "INSUFFICIENT_EVIDENCE"


def test_duplicate_case_identity_is_not_accepted():
    samples = sample_triplet()
    samples[2] = GridResult("fine", 64000, .40375, True, True, True, samples[0].case_hash)
    result = assess_grid_independence(samples, quantity="Cd")
    assert result["status"] == "INSUFFICIENT_EVIDENCE"


def test_gci_limit_enforced():
    result = assess_grid_independence(sample_triplet(values=(.70, .55, .475)),
                                      quantity="Cd", tolerance=.02)
    assert result["status"] == "NOT_GRID_INDEPENDENT"
    assert "GCI_ABOVE_TOLERANCE" in result["reasons"]
