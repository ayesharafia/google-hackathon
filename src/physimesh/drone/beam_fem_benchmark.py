import math
from itertools import pairwise

from .beam_fem import (
    _product,
    _quotient,
    _scaled,
    evaluate_solution,
    solve_beam,
)

_GAUSS5 = (
    (-0.9061798459386640, 0.2369268850561891),
    (-0.5384693101056831, 0.4786286704993665),
    (0.0, 0.5688888888888889),
    (0.5384693101056831, 0.4786286704993665),
    (0.9061798459386640, 0.2369268850561891),
)


def _finite(value):
    try:
        value = float(value)
    except OverflowError:
        raise ValueError("Benchmark finite-normal support exceeded.") from None
    if not math.isfinite(value):
        raise ValueError("Benchmark finite-normal support exceeded.")
    return value


def _order(coarse, fine):
    if coarse > fine > 0.0:
        return _finite((math.log(coarse) - math.log(fine)) / math.log(2.0))
    return None


def benchmark_refinement(
    *, length_m, E_pa, I_m4, outer_fibre_m, tip_force_n, uniform_load_n_m,
    mesh_elements=(1, 2, 4, 8, 16),
):
    """Compare reconstructed FEM fields with an independent EB reference."""
    if (
        type(mesh_elements) is not tuple or not 3 <= len(mesh_elements) <= 7
        or any(type(n) is not int or not 1 <= n <= 64 for n in mesh_elements)
        or any(b != 2 * a for a, b in pairwise(mesh_elements))
    ):
        raise ValueError("mesh_elements must contain 3–7 integers doubling within 1–64.")

    rows = []
    for n in mesh_elements:
        solution = solve_beam(
            length_m=length_m,
            E_pa=E_pa,
            I_m4=I_m4,
            outer_fibre_m=outer_fibre_m,
            tip_force_n=tip_force_n,
            uniform_load_n_m=uniform_load_n_m,
            elements=n,
        )
        if not rows:
            L, E, second_moment_m4, c = solution.L, solution.E, solution.second_moment_m4, solution.c
            P, q = float(tip_force_n), float(uniform_load_n_m)
            scale = stress_scale = pbar = qbar = 0.0
            force_total = moment_total = 0.0
            if P or q:
                qL = _product(q, L) if q else 0.0
                S = max(P, qL)
                scale = _quotient(_product(S, L, L, L), _product(E, second_moment_m4))
                curvature_scale = _quotient(_quotient(scale, L), L)
                stress_scale = _product(E, c, curvature_scale)
                pbar = _quotient(P, S) if P else 0.0
                qbar = _quotient(qL, S) if qL else 0.0
                PL = _product(P, L) if P else 0.0
                qL2_half = _quotient(_product(qL, L), 2.0) if q else 0.0
                force_total = _finite(P + qL)
                moment_total = _finite(PL + qL2_half)

        displacement_errors, stress_errors = [], []
        for element in range(n if scale else 0):
            for xi, weight in _GAUSS5:
                t = (xi + 1.0) / 2.0
                z = (element + t) / n
                z2 = _product(z, z)
                remaining = 1.0 - z
                wp = (
                    _quotient(_product(pbar, z2, 3.0 - z), 6.0)
                    if pbar else 0.0
                )
                wq = (
                    _quotient(
                        _product(qbar, z2, 6.0 - _product(4.0, z) + z2),
                        24.0,
                    )
                    if qbar else 0.0
                )
                sp = _product(pbar, remaining) if pbar else 0.0
                sq = (
                    _quotient(_product(qbar, remaining, remaining), 2.0)
                    if qbar else 0.0
                )
                reference_w = _scaled(_finite(wp + wq), scale)
                reference_stress = _scaled(_finite(sp + sq), stress_scale)
                field = evaluate_solution(solution, element, t)
                w = _finite(field.deflection_m)
                stress = _finite(field.nominal_bending_stress_pa)
                factor = math.sqrt(weight / (2 * n))
                displacement_errors.append(_scaled(_finite(w - reference_w), factor))
                stress_errors.append(_scaled(_finite(stress - reference_stress), factor))

        dw = _finite(math.hypot(*displacement_errors))
        ds = _finite(math.hypot(*stress_errors))
        force = _finite(solution.root_force_n)
        moment = _finite(solution.root_moment_nm)
        tip = evaluate_solution(solution, n - 1, 1.0)
        previous = rows[-1] if rows else None
        rows.append({
            "elements": n,
            "nodecount": n + 1,
            "tip_deflection_m": _finite(tip.deflection_m),
            "root_force_n": force,
            "root_moment_nm": moment,
            "force_balance_residual_n": _finite(force + force_total),
            "moment_balance_residual_nm": _finite(moment + moment_total),
            "linear_residual": _finite(solution.normalized_linear_residual),
            "numeric_rms_displacement_error_m": dw,
            "numeric_rms_nominal_stress_error_pa": ds,
            "observed_displacement_order": (
                _order(previous["numeric_rms_displacement_error_m"], dw)
                if previous and q else None
            ),
            "observed_stress_order": (
                _order(previous["numeric_rms_nominal_stress_error_pa"], ds)
                if previous and q else None
            ),
        })

    return {
        "status": "BENCHMARK_COMPUTED",
        "model_scope": "1D small-deflection constant-EI experimental",
        "physical_validation": "NOT_ESTABLISHED",
        "rows": rows,
        "notes": (
            "Analytical benchmark without experimental validation or acceptance decisions. "
            "Gauss5 exactly integrates squared quartic displacement errors (degree 8) "
            "and squared quadratic curvature errors (degree 4) in exact arithmetic. "
            "Normalized weighted hypot computes sqrt(integral(error²)/L). "
            "Pure-tip fields are exactly representable; their observed orders are "
            "omitted because roundoff orders are meaningless. Zero-load errors are zero. "
            "Finite-normal checks and residuals are computational diagnostics, "
            "not physical qualification or acceptance criteria."
        ),
    }
