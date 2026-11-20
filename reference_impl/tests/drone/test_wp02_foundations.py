import math

import numpy as np
import pytest

from physimesh.drone.provenance import Provenance, canonical_json, sha256_bytes, sha256_record
from physimesh.drone.units import (DIM_KINEMATIC_PRESSURE, DIM_PRESSURE_PA, UnitsError,
                                   length_factor, parse_foam_dimensions, to_si_length)
from physimesh.drone.frames import (MissingInput, RotorFrame, rotation_matrix_zyx,
                                    transform_axial_vectors, transform_tensor, transform_vectors)
from physimesh.drone.atmosphere import (check_altitude_pressure_consistency, isa_troposphere,
                                        make_atmosphere, tip_mach_screen)
from physimesh.drone.mass import CATEGORIES, MassItem, summarize


# ---------- provenance ----------
def test_sha256_of_empty_bytes_is_standard_value():
    assert sha256_bytes(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_record_hash_independent_of_key_order():
    assert sha256_record({"a": 1, "b": [1.5, 2]}) == sha256_record({"b": [1.5, 2], "a": 1})


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_null_backend_digest_blocks_execution():
    p = Provenance("drone_manifest_v1", "abc", "deadbeef", "2026-10-02T00:00:00Z",
                   backend_version="v2606", backend_image_digest=None)
    assert p.blocking_for_execution() == ["backend_image_digest"]


# ---------- units ----------
def test_null_source_unit_is_rejected_never_inferred():
    with pytest.raises(UnitsError, match="source_units is null"):
        length_factor(None)


def test_mm_conversion_is_recorded():
    v, rec = to_si_length(np.array([1000.0, 25.4]), "mm")
    assert np.allclose(v, [1.0, 0.0254])
    assert (rec.from_unit, rec.to_unit, rec.factor) == ("mm", "m", 1e-3)


def test_inch_is_exact():
    assert length_factor("in") == 0.0254


def test_parse_foam_dimensions_pressure_and_kinematic():
    assert parse_foam_dimensions("dimensions      [1 -1 -2 0 0 0 0];") == DIM_PRESSURE_PA
    assert parse_foam_dimensions("dimensions [0 2 -2 0 0];") == DIM_KINEMATIC_PRESSURE


# ---------- frames ----------
def test_yaw_90_maps_body_forward_to_world_north():
    r = rotation_matrix_zyx(math.pi / 2, 0.0, 0.0)
    assert np.allclose(transform_vectors(r, [1.0, 0.0, 0.0]), [0.0, 1.0, 0.0])


def test_axial_vector_flips_under_reflection_but_polar_does_not():
    h = np.diag([1.0, -1.0, 1.0])                 # mirror in the y = 0 plane
    assert np.allclose(transform_vectors(h, [0, 0, 10.0]), [0, 0, 10.0])
    assert np.allclose(transform_axial_vectors(h, [0, 0, 10.0]), [0, 0, -10.0])


def test_inertia_tensor_rotation():
    r = rotation_matrix_zyx(math.pi / 2, 0.0, 0.0)
    i_body = np.diag([1.0, 2.0, 3.0])
    assert np.allclose(transform_tensor(r, i_body), np.diag([2.0, 1.0, 3.0]))


def test_rotor_positive_rpm_right_hand_rule():
    rf = RotorFrame("r1", (0, 0, 0), (0, 0, 2.0), 60.0)
    assert np.allclose(rf.axis, (0, 0, 1))
    assert np.allclose(rf.omega_vector(), [0, 0, 2 * math.pi])


def test_rotor_null_rpm_blocks():
    with pytest.raises(MissingInput):
        RotorFrame("r1", (0, 0, 0), (0, 0, 1), None).omega_vector()


# ---------- atmosphere ----------
def test_isa_sea_level_density_and_sound_speed():
    p, t = isa_troposphere(0.0)
    atm = make_atmosphere(p, t, source="ISA troposphere", viscosity_law="sutherland")
    assert atm.density == pytest.approx(1.2250123, rel=1e-7)
    assert atm.speed_of_sound == pytest.approx(340.29229, rel=1e-7)
    assert atm.dynamic_viscosity_pa_s == pytest.approx(1.7892976e-5, rel=1e-7)
    assert atm.kinematic_viscosity == pytest.approx(1.4606365e-5, rel=1e-6)


def test_missing_pressure_blocks():
    with pytest.raises(MissingInput):
        make_atmosphere(None, 288.15, source="x", viscosity_pa_s=1.8e-5)


def test_inconsistent_altitude_and_pressure_rejected():
    with pytest.raises(ValueError, match="inconsistent"):
        check_altitude_pressure_consistency(2000.0, 101325.0, rel_tol=1e-3)


def test_tip_mach_screen_fixture():
    atm = make_atmosphere(101325.0, 288.15, source="ISA", viscosity_law="sutherland")
    omega = 500 * 2 * math.pi / 60
    assert tip_mach_screen(atm, omega, 1.0, 0.0) == pytest.approx(0.15386737, rel=1e-7)


# ---------- mass ----------
def _full_ledger(payload=750.0):
    return [
        MassItem("payload", "payload", payload, (0, 0, 0), ((0, 0, 0), (0, 0, 0), (0, 0, 0))),
        MassItem("frame", "structure", 1.0, (1, 0, 0), ((0, 0, 0), (0, 0, 0), (0, 0, 0))),
        MassItem("motors", "propulsion", 1.0, (-1, 0, 0), ((0, 0, 0), (0, 0, 0), (0, 0, 0))),
        MassItem("battery", "energy", 0.0, (0, 0, 0), ((0, 0, 0), (0, 0, 0), (0, 0, 0))),
        MassItem("fc", "avionics", 0.0, (0, 0, 0), ((0, 0, 0), (0, 0, 0), (0, 0, 0))),
        MassItem("misc", "other", 0.0, (0, 0, 0), ((0, 0, 0), (0, 0, 0), (0, 0, 0))),
    ]


def test_payload_weight_fixture():
    assert 750.0 * 9.80665 == pytest.approx(7354.9875, abs=1e-9)


def test_total_mass_cg_inertia_parallel_axis():
    s = summarize(_full_ledger(), need_inertia=True)
    assert s.complete
    assert s.total_mass_kg == pytest.approx(752.0)
    assert np.allclose(s.cg_body_m, [0, 0, 0])
    assert np.allclose(s.inertia_cg_body_kgm2, np.diag([0.0, 2.0, 2.0]))


def test_null_mass_gives_no_total():
    items = _full_ledger()
    items[1] = MassItem("frame", "structure", None, (1, 0, 0))
    s = summarize(items)
    assert s.total_mass_kg is None and "masses[frame].mass_kg" in s.missing


def test_missing_category_is_reported():
    items = [it for it in _full_ledger() if it.category != "energy"]
    s = summarize(items)
    assert any(m.startswith("masses.energy") for m in s.missing)


def test_payload_must_equal_requirement():
    s = summarize(_full_ledger(payload=700.0))
    assert not s.complete and "payload items sum to 700.0" in s.errors[0]
