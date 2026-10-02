"""Time windows, drift and grid-convergence. Implements [M-E37], [M-E39], [M-E40]."""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


def _trapz(y, x):
    y = np.asarray(y, float); x = np.asarray(x, float)
    return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(x)))


@dataclass(frozen=True)
class WindowStats:
    t_start: float
    t_end: float
    mean: float
    rms_fluct: float
    n_samples: int


def window_stats(t: np.ndarray, f: np.ndarray, t1: float, t2: float) -> WindowStats:
    """Time-weighted mean and RMS fluctuation over [t1, t2] [M-E37]."""
    t = np.asarray(t, float); f = np.asarray(f, float)
    m = (t >= t1 - 1e-15) & (t <= t2 + 1e-15)
    if m.sum() < 3:
        raise ValueError("fewer than 3 samples in window")
    tt, ff = t[m], f[m]
    dur = tt[-1] - tt[0]
    mean = _trapz(ff, tt) / dur
    rms = math.sqrt(_trapz((ff - mean) ** 2, tt) / dur)
    return WindowStats(float(tt[0]), float(tt[-1]), mean, rms, int(m.sum()))


def revolution_windows(t: np.ndarray, f: np.ndarray, rev_period_s: float, *,
                       discard_revs: int, revs_per_window: int) -> list[WindowStats]:
    """Consecutive complete-revolution windows after the start-up discard [M§15]."""
    t = np.asarray(t, float)
    start = t[0] + discard_revs * rev_period_s
    w = revs_per_window * rev_period_s
    out = []
    k = 0
    while start + (k + 1) * w <= t[-1] + 1e-12:
        out.append(window_stats(t, f, start + k * w, start + (k + 1) * w))
        k += 1
    return out


def drift(windows: Sequence[WindowStats], abs_scale: float) -> float:
    """Relative change between the last two windows; abs_scale protects near-zero loads."""
    if len(windows) < 2:
        raise ValueError("need at least two complete windows")
    a, b = windows[-2].mean, windows[-1].mean
    return abs(b - a) / max(abs(b), abs_scale)


@dataclass(frozen=True)
class GridConvergence:
    observed_order: float
    extrapolated: float
    gci_fine: float
    behaviour: str        # "monotonic" | "oscillatory" | "divergent"


def grid_convergence(f1: float, f2: float, f3: float, r: float, fs: float = 1.25) -> GridConvergence:
    """f1 finest, constant refinement ratio r > 1 [M-E39], [M-E40], [R6].
    Oscillatory or divergent behaviour is reported, never forced into a GCI."""
    if r <= 1:
        raise ValueError("refinement ratio must be > 1")
    e21, e32 = f2 - f1, f3 - f2
    if e21 == 0 or e32 == 0:
        raise ValueError("zero difference: use another nonzero scale [M§15]")
    ratio = e32 / e21
    if ratio < 0:
        return GridConvergence(float("nan"), float("nan"), float("nan"), "oscillatory")
    po = math.log(ratio) / math.log(r)
    if po <= 0:
        return GridConvergence(po, float("nan"), float("nan"), "divergent")
    fext = f1 + (f1 - f2) / (r ** po - 1.0)
    gci = fs * abs((f1 - f2) / f1) / (r ** po - 1.0)
    return GridConvergence(po, fext, gci, "monotonic")


def effective_refinement_ratio(volume_m3: float, n_coarse: int, n_fine: int) -> float:
    """3-D effective length h = (V/N)^(1/3) [M§15]."""
    return ((volume_m3 / n_coarse) / (volume_m3 / n_fine)) ** (1.0 / 3.0)
