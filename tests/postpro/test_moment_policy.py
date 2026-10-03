import numpy as np
import pytest

from physimesh.postpro.loads3d import integrate_surface_loads, moment_absolute_floor, reconcile


def test_asymmetric_load_moments_match_independent_hand_calculation():
    # Forces (-2,0,0) at (0,2,1), (0,-3,0) at (1,0,2):
    # r cross F = (0,-2,4) + (6,0,-3) = (6,-2,1) N m.
    loads = integrate_surface_loads(np.array([[0, 2, 1], [1, 0, 2]]),
                                    np.array([[1, 0, 0], [0, 1, 0]]), np.array([2, 3]),
                                    np.zeros((2, 3)), [0, 0, 0], 0)
    np.testing.assert_array_equal(loads.moment_total_nm, [6, -2, 1])
    np.testing.assert_array_equal(loads.force_total_n, [-2, -3, 0])
    shifted = integrate_surface_loads(np.array([[0, 2, 1], [1, 0, 2]]),
                                      np.array([[1, 0, 0], [0, 1, 0]]), np.array([2, 3]),
                                      np.zeros((2, 3)), [1, 0, 0], 0)
    np.testing.assert_array_equal(shifted.moment_total_nm, [6, -2, 4])
    floor = moment_absolute_floor(force_reference_n=5, length_reference_m=2)
    assert reconcile(loads.moment_total_nm, np.array([6, -2, 1]), rel_tol=1e-3, abs_tol=floor).passed
    for corrupted in (np.array([-6, 2, -1]), np.array([12, -4, 2]), shifted.moment_total_nm):
        assert not reconcile(loads.moment_total_nm, corrupted, rel_tol=1e-3, abs_tol=floor).passed


def test_floor_scales_with_force_length_and_resolves_microtorques():
    floor = moment_absolute_floor(force_reference_n=.4, length_reference_m=1)
    assert floor == pytest.approx(4e-10)
    assert not reconcile(np.array([4e-6]), np.array([0.]), rel_tol=1e-3, abs_tol=floor).passed
    assert reconcile(np.array([1e-15]), np.array([0.]), rel_tol=1e-3, abs_tol=floor).passed
    assert moment_absolute_floor(force_reference_n=4, length_reference_m=2) == pytest.approx(20*floor)


@pytest.mark.parametrize('force,length', [(0, 1), (1, -1), (float('inf'), 1), (True, 1)])
def test_reference_scales_must_be_independent_and_physical(force, length):
    with pytest.raises(ValueError):
        moment_absolute_floor(force_reference_n=force, length_reference_m=length)
