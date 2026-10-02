from dataclasses import fields, replace

import numpy as np
import pytest

from physimesh.drone.demo_geometry import binary_stl_bytes, icosphere_triangles
from physimesh.solver.openfoam_cases import (
    ExternalSteadySpec,
    external_steady_case,
    refinement_levels,
    translated_settings,
)


def demo_spec():
    return ExternalSteadySpec(
        binary_stl_bytes(icosphere_triangles(1.0, 5)), "sphere",
        (-10., -10., -10.), (30., 10., 10.), (64, 32, 32), (4, 4),
        (1., 0., 0.), 0.01, np.pi / 4, 1., (-9.731, 0.123, 0.137),
        3000, (0., 1., 0.), ((0.6, 0., 0.), (10., 0., 0.), 201),
    )


def test_case_is_deterministic_and_has_template_provenance():
    spec = demo_spec()
    files = external_steady_case(spec)
    assert files == external_steady_case(spec)
    assert files["constant/triSurface/sphere.stl"] == spec.stl_bytes
    for name, raw in files.items():
        if name.startswith(("system/", "0/", "constant/")) and not name.endswith(".stl"):
            assert raw.startswith(b"// Source: v2606 tutorials/"), name
    control = files["system/controlDict"].decode()
    assert "writeFormat     ascii;" in control
    assert "purgeWrite      1;" in control
    assert "simulationType      laminar;" in files["constant/turbulenceProperties"].decode()


def test_translation_covers_every_spec_field_and_demo_reynolds_number():
    spec = demo_spec()
    translation = translated_settings(spec)
    assert {field.name for field in fields(spec)} <= set(translation)
    for field in fields(spec):
        assert {"file", "key", "value"} <= set(translation[field.name])
    assert np.linalg.norm(spec.u_inf_m_s) * spec.l_ref_m / spec.nu_m2_s == pytest.approx(100)


def test_refinement_changes_only_background_divisions():
    spec = demo_spec()
    levels = refinement_levels(spec, 1.5, 3)
    assert [level.background_divisions for level in levels] == [(64, 32, 32), (96, 48, 48), (144, 72, 72)]
    for level in levels:
        assert replace(level, background_divisions=spec.background_divisions) == spec


@pytest.mark.parametrize("location", [(0, 0, 0), (40, 0, 0)])
def test_location_in_mesh_must_be_outside_body_and_inside_domain(location):
    with pytest.raises(ValueError, match="location_in_mesh"):
        external_steady_case(replace(demo_spec(), location_in_mesh_m=location))
