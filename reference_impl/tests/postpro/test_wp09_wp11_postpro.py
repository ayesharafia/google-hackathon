import math

import numpy as np
import pytest

from physimesh.postpro.contour_rules import CapabilityManifest, compute_range, select_evidence
from physimesh.postpro.statistics import (drift, effective_refinement_ratio, grid_convergence,
                                          revolution_windows, window_stats)


# ---------- statistics ----------
def test_window_mean_and_rms_of_sinusoid():
    t = np.linspace(0, 1, 20001)
    f = 100 + 5 * np.sin(2 * math.pi * 10 * t)
    w = window_stats(t, f, 0.0, 1.0)
    assert w.mean == pytest.approx(100, abs=1e-6)
    assert w.rms_fluct == pytest.approx(5 / math.sqrt(2), rel=1e-6)


def test_revolution_windows_and_drift():
    period = 0.06
    t = np.arange(0, 20 * period + 1e-12, period / 360)
    f = 1000 * (1 - np.exp(-t / 0.05)) + 3 * np.sin(2 * math.pi * t / period)
    wins = revolution_windows(t, f, period, discard_revs=5, revs_per_window=5)
    assert len(wins) == 3
    assert drift(wins, abs_scale=1.0) < 0.005          # 0.5 % gate [M§32]


def test_gci_fixture():
    g = grid_convergence(100.0, 101.0, 103.0, 2.0)
    assert (g.observed_order, g.extrapolated, g.gci_fine) == pytest.approx((1.0, 99.0, 0.0125))


def test_oscillatory_convergence_not_forced_into_gci():
    assert grid_convergence(100.0, 101.0, 99.0, 2.0).behaviour == "oscillatory"


def test_effective_ratio_3d():
    assert effective_refinement_ratio(1.0, 1_000_000, 8_000_000) == pytest.approx(2.0)


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
