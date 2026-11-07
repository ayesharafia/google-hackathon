from dataclasses import FrozenInstanceError

import pytest

from physimesh.drone.beam_fem import evaluate_solution, solve_beam
from physimesh.drone.beam_fem_benchmark import benchmark_refinement

BASE = {
    "length_m": 2., "E_pa": 70e9, "I_m4": 1e-6,
    "outer_fibre_m": .01, "tip_force_n": 10., "uniform_load_n_m": 100.,
}
FIELDS = (
    "deflection_m", "rotation_rad", "curvature_1_m",
    "nominal_bending_stress_pa",
)
REACTIONS = ("root_force_n", "root_moment_nm")


@pytest.mark.parametrize("changes", [
    {"length_m": 1e200},
    {"E_pa": 1e308, "I_m4": 1e308},
    {"tip_force_n": 1e308},
    {"uniform_load_n_m": 1e308},
    {"length_m": 1e-200},
    {"I_m4": 1e-320},
    {"tip_force_n": 1e-310, "uniform_load_n_m": 0.},
    {"length_m": 10**1000},
])
@pytest.mark.parametrize("run,mesh", [
    (solve_beam, {"elements": 8}),
    (benchmark_refinement, {"mesh_elements": (1, 2, 4)}),
])
def test_nonconservative_numeric_domain_rejected(changes, run, mesh):
    with pytest.raises(ValueError):
        run(**{**BASE, **changes, **mesh})


def test_stress_overflow_rejected():
    params = {**BASE, "outer_fibre_m": 1e308}
    sol = solve_beam(**params)
    with pytest.raises(ValueError):
        evaluate_solution(sol, 3, .37)
    with pytest.raises(ValueError):
        benchmark_refinement(**params, mesh_elements=(1, 2, 4))


def test_extreme_zero_load():
    params = {
        "length_m": 1e200, "E_pa": 1e308, "I_m4": 1e308,
        "outer_fibre_m": 1e200, "tip_force_n": 0., "uniform_load_n_m": 0.,
    }
    sol = solve_beam(**params)
    assert all(getattr(sol, name) == 0. for name in REACTIONS)
    for element, coordinate, x in [(0, 0., 0.), (7, 1., 1e200)]:
        point = evaluate_solution(sol, element, coordinate)
        assert all(getattr(point, name) == 0. for name in FIELDS)
        assert point.x_m == pytest.approx(x)
    rows = benchmark_refinement(**params, mesh_elements=(1, 2, 4))["rows"]
    assert len(rows) == 3
    for row in rows:
        assert row["numeric_rms_displacement_error_m"] == 0.
        assert row["numeric_rms_nominal_stress_error_pa"] == 0.
        assert row["observed_displacement_order"] is None
        assert row["observed_stress_order"] is None


def test_clamp_continuity_frozen_and_tiny_coordinate():
    sol = solve_beam(**BASE)
    root = evaluate_solution(sol, 0, 0.)
    assert root.deflection_m == 0.
    assert root.rotation_rad == 0.
    for j in range(7):
        left = evaluate_solution(sol, j, 1.)
        right = evaluate_solution(sol, j + 1, 0.)
        for name in FIELDS[:2]:
            assert getattr(left, name) == pytest.approx(
                getattr(right, name), rel=0., abs=1e-12)
    with pytest.raises(FrozenInstanceError):
        sol.n = sol.n
    with pytest.raises(ValueError):
        evaluate_solution(sol, 3, 1e-200)


@pytest.mark.parametrize("changes,factors,reaction_factor", [
    ({"tip_force_n": 30., "uniform_load_n_m": 300.}, (3.,) * 4, 3.),
    ({"E_pa": 140e9}, (.5, .5, .5, 1.), 1.),
    ({"I_m4": 2e-6}, (.5,) * 4, 1.),
])
def test_scaling(changes, factors, reaction_factor):
    base = solve_beam(**BASE)
    scaled = solve_beam(**{**BASE, **changes})
    a, b = evaluate_solution(base, 3, .37), evaluate_solution(scaled, 3, .37)
    for name, factor in zip(FIELDS + REACTIONS, factors + (reaction_factor,) * 2):
        original, changed = (a, b) if name in FIELDS else (base, scaled)
        assert getattr(changed, name) == pytest.approx(
            factor * getattr(original, name), rel=1e-7, abs=1e-12)
