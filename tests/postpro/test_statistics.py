import math

import numpy as np
import pytest

from physimesh.postpro.statistics import (
    drift,
    effective_refinement_ratio,
    grid_convergence,
    revolution_windows,
    window_stats,
)


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


