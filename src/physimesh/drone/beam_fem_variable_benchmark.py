"""Experimental manufactured-solution (MMS) benchmark; no physical validation."""

import math
import sys
from dataclasses import astuple
from itertools import pairwise

from .beam_fem_variable import (
    _normal,
    _number,
    _product,
    _quotient,
    _sum,
    evaluate_variable_solution,
    solve_beam_variable,
)


def benchmark_variable_mms(*, length_m, E_pa, I_root_m4, outer_fibre_m,
                           deflection_scale_m, mesh_nodes):
    L = _number(length_m, "length_m", True)
    E = _number(E_pa, "E_pa", True)
    I_root = _number(I_root_m4, "I_root_m4", True)
    c = _number(outer_fibre_m, "outer_fibre_m", True)
    w0 = _normal(_number(deflection_scale_m, "deflection_scale_m", True))
    if type(mesh_nodes) is not tuple:
        raise TypeError("mesh_nodes must be a built-in tuple")
    if not 2 <= len(mesh_nodes) <= 7:
        raise ValueError("mesh_nodes must contain 2..7 meshes")
    for nodes in mesh_nodes:
        if type(nodes) is not tuple:
            raise TypeError("Each mesh must be a built-in tuple")
        if not 2 <= len(nodes) <= 65:
            raise ValueError("Each mesh must contain 2..65 nodes")
    meshes, sizes, inertias = [], [], []
    for nodes in mesh_nodes:
        nodes = tuple(_number(x, "mesh node", False) for x in nodes)
        if nodes[0] != 0.0 or nodes[-1] != L:
            raise ValueError("Each mesh must start at zero and end at length_m")
        if any(b <= a for a, b in pairwise(nodes)):
            raise ValueError("Mesh nodes must be strictly increasing")
        lengths = tuple(_normal(b - a) for a, b in pairwise(nodes))
        hmax = max(lengths)
        if sizes and hmax >= sizes[-1]:
            raise ValueError("Mesh maximum element lengths must strictly decrease")
        meshes.append(nodes)
        sizes.append(hmax)
        inertias.append(tuple(_product(I_root, 1.0 + (x / L) / 2.0)
                              for x in nodes))
    EI = _product(E, I_root)
    rotation_scale = _quotient(w0, L)
    stress_scale = _product(E, c, _quotient(rotation_scale, L))
    qtip = _product(36.0, EI, w0)
    for _ in range(4):
        qtip = _quotient(qtip, L)
    exact_force = _product(18.0, EI, w0)
    for _ in range(3):
        exact_force = _quotient(exact_force, L)
    exact_moment = _quotient(_quotient(_product(12.0, EI, w0), L), L)
    exact_tip = _product(3.0, w0)
    scales = (w0, rotation_scale, stress_scale)
    floors = tuple(_product(64.0 * sys.float_info.epsilon, s) for s in scales)
    solutions = [solve_beam_variable(
        length_m=L, E_pa=E, second_moments_m4=moments, nodes_m=nodes,
        outer_fibre_m=c, tip_force_n=0.0, uniform_load_n_m=0.0,
        ramp_load_root_n_m=0.0, ramp_load_tip_n_m=qtip, tip_moment_n_m=0.0,
    ) for nodes, moments in zip(meshes, inertias)]
    gauss = ((-0.906179845938664, 0.236926885056189),
             (-0.538469310105683, 0.4786286704993665),
             (0.0, 0.568888888888889),
             (0.538469310105683, 0.4786286704993665),
             (0.906179845938664, 0.236926885056189))

    def finite(value):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Benchmark arithmetic must remain finite")
        if value:
            _normal(abs(value))
        return value

    rows, previous = [], None
    for sol, nodes, hmax in zip(solutions, meshes, sizes):
        terms = [[], [], []]
        for i, (left, right) in enumerate(pairwise(nodes)):
            h = _normal(right - left)
            for xi, weight in gauss:
                t = (1.0 + xi) / 2.0
                x, w, theta, curvature, stress = astuple(
                    evaluate_variable_solution(sol, i, t))
                x, w, theta, curvature, stress = map(
                    finite, (x, w, theta, curvature, stress))
                z = _quotient(x, L)
                references = (
                    _product(w0, z, z, 6.0 - 4.0*z + z*z),
                    _product(rotation_scale, z, 12.0 - 12.0*z + 4.0*z*z),
                    _product(stress_scale, 12.0, 1.0-z, 1.0-z),
                )
                factor = math.sqrt(_product(weight, 0.5, _quotient(h, L)))
                for values, actual, reference in zip(
                        terms, (w, theta, stress), references):
                    error = _sum((actual, -reference))
                    values.append(_product(abs(error), factor) if error else 0.0)
        errors = tuple(finite(math.hypot(*values)) for values in terms)
        orders = [None, None, None]
        if previous is not None:
            previous_h, previous_errors = previous
            denominator = _normal(math.log(previous_h) - math.log(hmax))
            for j, (old, new, floor) in enumerate(zip(previous_errors, errors, floors)):
                if old > new and old > floor and new > floor:
                    orders[j] = finite((math.log(old) - math.log(new)) / denominator)
        rows.append({
            "elements": sol.n,
            "max_element_length_m": finite(hmax),
            "tip_deflection_m": finite(sol.displacements[-1]),
            "root_force_n": finite(sol.root_force_n),
            "root_moment_nm": finite(sol.root_moment_nm),
            "displacement_rms_error_m": errors[0],
            "rotation_rms_error_rad": errors[1],
            "stress_rms_error_pa": errors[2],
            "displacement_order": orders[0],
            "rotation_order": orders[1],
            "stress_order": orders[2],
            "normalized_linear_residual": finite(sol.normalized_linear_residual),
        })
        previous = hmax, errors
    return {
        "schema_version": "variable_beam_mms_refinement_v1",
        "reference_kind": "manufactured_quartic_exact_linear_inertia",
        "physical_validation": "NOT_ESTABLISHED",
        "evidence_level": "unverified",
        "feasibility": None,
        "aircraft_status": None,
        "ramp_tip_load_n_m": qtip,
        "exact_tip_deflection_m": exact_tip,
        "exact_root_force_n": -exact_force,
        "exact_root_moment_nm": -exact_moment,
        "rows": rows,
        "output_units": {
            "elements": "1", "max_element_length_m": "m",
            "tip_deflection_m": "m", "root_force_n": "N",
            "root_moment_nm": "N m", "displacement_rms_error_m": "m",
            "rotation_rms_error_rad": "rad", "stress_rms_error_pa": "Pa",
            "displacement_order": "1", "rotation_order": "1", "stress_order": "1",
            "normalized_linear_residual": "1", "ramp_tip_load_n_m": "N/m",
            "exact_tip_deflection_m": "m", "exact_root_force_n": "N",
            "exact_root_moment_nm": "N m",
        },
        "limitations": [
            (
                "Fixed linear inertia I(x)=I_root*(1+x/(2L)) and manufactured ramp load only; "
                "these results do not establish arbitrary-profile accuracy or physical validation."
            ),
            "RMS errors are numerical five-point Gauss quadrature values over physical elements.",
            "Orders use maximum element lengths, including graded meshes, rather than L/n.",
            (
                "The 64*epsilon*natural-field-scale arithmetic floors are reporting heuristics, "
                "not proofs or pass/fail tolerances; nondecreasing or floor-level errors give null orders."
            ),
            "No fourth-order convergence promise for smooth nonlinear inertia profiles is made.",
        ],
        "sources": [
            "https://ceae.colorado.edu/~regueiro/courses/CVEN4511_5511_notes.pdf",
            "https://www.osti.gov/biblio/759450",
        ],
    }
