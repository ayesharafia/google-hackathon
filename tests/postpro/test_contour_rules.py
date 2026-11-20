import numpy as np
import pytest

from physimesh.postpro.contour_rules import CapabilityManifest, compute_range, select_evidence

# ---------- contour rules (table [M§33]) ----------
WALLS = CapabilityManifest(True, False, "kinematic", True, "absolute", True, True, True, True,
                           True, True, True, reference_speed_m_s=None)
DISKS = CapabilityManifest(False, True, "kinematic", True, "absolute", True, True, True, False,
                           True, True, True, reference_speed_m_s=None)


def ids(plan):
    return [p.field_id for p in plan.selected]


def test_payload_lift_with_blade_walls():
    p = select_evidence("payload_lift", WALLS)
    assert "traction.world_z" in ids(p) and "balance.E05" in ids(p) and p.complete
    assert any("pressure magnitude alone" in r for r in p.rejected)


def test_payload_lift_with_disks_never_invents_blade_pressure():          # CT05
    p = select_evidence("payload_lift", DISKS, requested=["blade_pressure"])
    assert "source.rotor_reaction" in ids(p)
    assert any("source-only" in r for r in p.rejected)
    assert any(m.item == "blade surface" for m in p.missing)


def test_rotor_power_selects_axial_moment_and_signed_power():
    p = select_evidence("rotor_power", WALLS)
    assert {"moment_density.rotor_axial", "load.torque_history", "load.shaft_power_signed"} <= set(ids(p))
    assert any("speed contour" in r for r in p.rejected)


def test_ct03_cp_rejected_at_zero_reference():
    p = select_evidence("body_download", WALLS, requested=["cp"])
    assert any("Cp with zero reference speed" in r for r in p.rejected)
    assert "pressure.static_gauge" in ids(p) and "pressure.cp" not in ids(p)


def test_ct03_cp_allowed_with_declared_tip_speed():
    cap = CapabilityManifest(**{**WALLS.__dict__, "reference_speed_m_s": 150.0})
    assert "pressure.cp" in ids(select_evidence("body_download", cap, requested=["cp"]))


def test_unknown_pressure_semantics_blocks_traction():
    cap = CapabilityManifest(**{**WALLS.__dict__, "pressure_kind": None})
    p = select_evidence("payload_lift", cap)
    assert "traction.world_z" not in ids(p) and not p.complete


def test_ct07_unaccepted_window_blocks_mean_plots():
    cap = CapabilityManifest(**{**WALLS.__dict__, "accepted_time_window": False})
    p = select_evidence("payload_lift", cap, time_mode="mean")
    assert not p.complete and any("averaging window" in r for r in p.rejected)


def test_yplus_rejected_for_laminar():
    cap = CapabilityManifest(**{**WALLS.__dict__, "turbulent_walls": False})
    p = select_evidence("numerical_quality", cap)
    assert "mesh.y_plus" not in ids(p)


# ---------- range policy ----------
def test_ct01_equal_fields_on_different_meshes_share_legend():
    a = np.linspace(-50, 50, 101)                     # coarse mesh samples
    b = np.linspace(-50, 50, 1001)                    # fine mesh, same field
    shared = compute_range("shared_global", [a, b])
    assert (shared.vmin, shared.vmax) == (-50.0, 50.0)


def test_ct08_percentile_clipping_reports_extrema_and_fraction():
    v = np.concatenate([np.zeros(98), [1000.0, -1000.0]])
    r = compute_range("single_full_range", [v], percentile=98.0)
    assert r.true_max == 1000.0 and r.true_min == -1000.0
    assert r.clipped_fraction == pytest.approx(0.02)


def test_nans_counted_not_hidden():
    r = compute_range("single_full_range", [np.array([1.0, np.nan, 2.0])])
    assert r.invalid_count == 1 and (r.vmin, r.vmax) == (1.0, 2.0)


@pytest.mark.parametrize('fields,weights,percentile', [
    ([], None, None), ([np.array([np.nan])], None, None),
    ([np.array([1, 2])], [np.array([1])], None),
    ([np.array([1, 2])], [np.array([-1, 2])], None),
    ([np.array([1, 2])], [np.array([0, 0])], None),
    ([np.array([1, 2])], None, 49),
])
def test_invalid_range_evidence_refused(fields, weights, percentile):
    with pytest.raises(ValueError):
        compute_range('shared_global', fields, weights=weights, percentile=percentile)
