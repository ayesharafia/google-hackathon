"""Numerical sample-envelope checks; these do not validate physical performance."""

import numpy as np
import pytest

from physimesh.drone.conditioning import upper_envelope


def pairwise_minorant(x, target):
    """Enumerate all chords bracketing each sample, including the sample itself."""
    lower = np.empty(len(x), dtype=float)
    for i in range(len(x)):
        candidates = [float(target[i])]
        for left in range(i + 1):
            for right in range(i, len(x)):
                if left == right:
                    continue
                weight = (x[i] - x[left]) / (x[right] - x[left])
                candidates.append(
                    (1.0 - weight) * target[left] + weight * target[right]
                )
        lower[i] = min(candidates)
    return lower


def tolerance(*values):
    scale = max(1.0, *(float(np.max(np.abs(v))) for v in values))
    return 512 * np.finfo(float).eps * scale


def check_contract(x, target):
    x = np.asarray(x, dtype=float)
    target = np.asarray(target, dtype=float)
    lower = pairwise_minorant(x, target)
    expected_shift = float(np.max(target - lower))
    power, shift = upper_envelope(x, target)
    power = np.asarray(power)
    tol = tolerance(target, lower, power)

    assert power.shape == target.shape
    assert np.isfinite(power).all()
    assert np.isfinite(shift)
    assert shift >= 0.0
    assert abs(shift - expected_shift) <= tol
    np.testing.assert_allclose(
        power, lower + expected_shift, rtol=0, atol=tol
    )
    assert np.all(power >= target - tol)

    dx = np.diff(x)
    slopes = np.diff(power) / dx
    slope_error = 2 * tol / dx
    assert np.all(
        np.diff(slopes) >= -(slope_error[:-1] + slope_error[1:])
    )
    if np.all(np.diff(target) >= 0):
        assert np.all(slopes >= -slope_error)
    return power, shift


@pytest.mark.parametrize("seed", [0, 17, 2026])
@pytest.mark.parametrize("n", range(2, 21))
def test_random_sample_envelopes(seed, n):
    rng = np.random.default_rng(seed * 100 + n)
    gaps = rng.uniform(1, 100, n - 1)
    x = np.r_[1.0, 1.0 + np.cumsum(gaps)]
    target = rng.uniform(1, 10000, n)
    check_contract(x, target)
    check_contract(x, np.sort(target))


@pytest.mark.parametrize("target", [[1, 10000], [10000, 1], [0, 0]])
def test_two_points_require_no_shift(target):
    power, shift = check_contract([1, 10000], target)
    assert shift == 0.0
    np.testing.assert_array_equal(power, target)


def test_convex_input_requires_no_shift():
    x = np.array([1, 2, 5, 11, 23], dtype=float)
    target = x**2 + 3
    power, shift = check_contract(x, target)
    assert shift == 0.0
    np.testing.assert_array_equal(power, target)


def test_concave_input_requires_positive_shift():
    x = np.array([1, 2, 4, 7], dtype=float)
    target = np.array([1, 5, 9, 12], dtype=float)
    _, shift = check_contract(x, target)
    assert shift > tolerance(target)


def test_piecewise_target_matches_exact_oracle():
    x = np.array([1, 2, 4, 7, 10], dtype=float)
    target = np.array([2, 7, 5, 11, 14], dtype=float)
    lower = np.array([2, 3, 5, 9.5, 14])
    np.testing.assert_allclose(pairwise_minorant(x, target), lower, atol=0)
    power, shift = check_contract(x, target)
    assert shift == 4.0
    np.testing.assert_array_equal(power, lower + 4)


def test_interior_collinear_samples():
    x = np.array([1, 2, 4, 7, 9], dtype=float)
    target = np.array([2, 4, 8, 20, 28], dtype=float)
    power, shift = check_contract(x, target)
    assert shift == 0.0
    np.testing.assert_array_equal(power, target)


def test_decreasing_target_can_have_negative_envelope_slopes():
    power, shift = check_contract([1, 3, 8], [9, 5, 0])
    assert shift == 0.0
    assert np.all(np.diff(power) < 0)


@pytest.mark.parametrize("seed", [3, 41, 99])
def test_positive_affine_coordinate_invariance(seed):
    rng = np.random.default_rng(seed)
    x = np.r_[1.0, 1.0 + np.cumsum(rng.uniform(1, 20, 11))]
    target = rng.uniform(1, 1000, len(x))
    power, shift = check_contract(x, target)

    moved_power, moved_shift = check_contract(3.25 * x + 17, target)
    tol = tolerance(power, moved_power)
    np.testing.assert_allclose(moved_power, power, rtol=0, atol=tol)
    assert abs(moved_shift - shift) <= tol

    scaled_power, scaled_shift = check_contract(x, 2.5 * target + 13)
    tol = tolerance(scaled_power, 2.5 * power + 13)
    np.testing.assert_allclose(
        scaled_power, 2.5 * power + 13, rtol=0, atol=tol
    )
    assert abs(scaled_shift - 2.5 * shift) <= tol
