"""Contract tests for the variable-section beam MMS benchmark."""

import copy
import json
import math

import pytest

from physimesh.drone.beam_fem_variable_benchmark import benchmark_variable_mms


@pytest.fixture
def benchmark_args():
    return {
        "length_m": 2,
        "E_pa": 70e9,
        "I_root_m4": 1e-6,
        "outer_fibre_m": 0.01,
        "deflection_scale_m": 0.001,
        "mesh_nodes": tuple(
            tuple(2 * i / n for i in range(n + 1)) for n in (4, 8, 16)
        ),
    }


def test_result_metadata_schema_root_references_and_convergence(benchmark_args):
    result = benchmark_variable_mms(**benchmark_args)

    assert isinstance(result, dict)
    assert result["schema_version"] == "variable_beam_mms_refinement_v1"
    assert result["reference_kind"] == "manufactured_quartic_exact_linear_inertia"
    assert result["physical_validation"] == "NOT_ESTABLISHED"
    assert result["evidence_level"] == "unverified"
    assert result["feasibility"] is None
    assert result["aircraft_status"] is None

    assert result["ramp_tip_load_n_m"] == pytest.approx(157.5)
    assert result["exact_tip_deflection_m"] == pytest.approx(0.003)
    assert result["exact_root_force_n"] == pytest.approx(-157.5)
    assert result["exact_root_moment_nm"] == pytest.approx(-210)

    rows = result["rows"]
    assert len(rows) == 3
    for row, elements in zip(rows, (4, 8, 16)):
        assert row["elements"] == elements
        assert row["max_element_length_m"] == pytest.approx(2 / elements)
        assert row["root_force_n"] == pytest.approx(
            -157.5, rel=0, abs=1e-7
        )
        assert row["root_moment_nm"] == pytest.approx(
            -210, rel=0, abs=1e-7
        )

    for field in ("displacement_order", "rotation_order", "stress_order"):
        assert rows[0][field] is None
    assert 3.8 <= rows[-1]["displacement_order"] <= 4.2
    assert 2.8 <= rows[-1]["rotation_order"] <= 3.2
    assert 1.8 <= rows[-1]["stress_order"] <= 2.2

    # Strict JSON rejects non-finite floats anywhere in the returned document.
    encoded = json.dumps(result, allow_nan=False)
    assert json.loads(encoded) == result


def test_repeat_determinism_and_no_input_mutation(benchmark_args):
    original = copy.deepcopy(benchmark_args)

    first = benchmark_variable_mms(**benchmark_args)
    assert benchmark_args == original
    second = benchmark_variable_mms(**benchmark_args)

    assert benchmark_args == original
    assert first == second
    assert json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(
        second, sort_keys=True, allow_nan=False
    )


@pytest.mark.parametrize(
    "deflection_scale_m",
    [True, "x", 0, -1, math.nan, math.inf, 10**1000],
    ids=["bool", "string", "zero", "negative", "nan", "infinity", "huge-int"],
)
def test_bad_deflection_scale(benchmark_args, deflection_scale_m):
    benchmark_args["deflection_scale_m"] = deflection_scale_m
    with pytest.raises((TypeError, ValueError)):
        benchmark_variable_mms(**benchmark_args)


@pytest.mark.parametrize(
    "invalid_family",
    ["list", "one-mesh", "duplicate-family", "reversed-family", "nonstrict-nodes"],
)
def test_bad_meshes(benchmark_args, invalid_family):
    meshes = benchmark_args["mesh_nodes"]
    if invalid_family == "list":
        bad_meshes = list(meshes)
    elif invalid_family == "one-mesh":
        bad_meshes = meshes[:1]
    elif invalid_family == "duplicate-family":
        bad_meshes = (meshes[0], meshes[0], meshes[2])
    elif invalid_family == "reversed-family":
        bad_meshes = meshes[::-1]
    else:
        bad_meshes = ((0.0, 0.5, 0.5, 1.5, 2.0), *meshes[1:])

    benchmark_args["mesh_nodes"] = bad_meshes
    with pytest.raises((TypeError, ValueError)):
        benchmark_variable_mms(**benchmark_args)
