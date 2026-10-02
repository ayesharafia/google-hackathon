"""Native captured sphere evidence and analytical unequal-grid checks."""
from pathlib import Path

import pytest

from physimesh.postpro.results import sphere_load_result
from physimesh.postpro.statistics import grid_convergence_unequal, order_capped_gci

FIXTURE = Path(__file__).parents[1] / 'solver/fixtures/sphere_coarse'


def test_captured_surface_integral_matches_native_force_moment_and_cd():
    result = sphere_load_result(FIXTURE, '812', rho=1, speed=1, diameter=1)
    assert result['reconciliation']['status'] == 'accepted'
    assert set(result['reconciliation']['checks']) == {'pressure', 'viscous', 'total', 'moment', 'cd'}
    assert all(check['passed'] for check in result['reconciliation']['checks'].values())
    assert result['force_viscous_n'][0] > 0
    assert result['force_pressure_n'][0] > 0
    assert result['convergence']['passed']
    assert result['convergence']['windows'][-1]['n_samples'] == 201
    assert result['evidence'] == 'unverified'  # numerical checks do not create independent signoff


def test_gci_recovers_known_second_order_on_unequal_meshes():
    h1, h2, h3 = 0.1, 0.16, 0.23
    values = [2 + 3*h*h for h in (h1, h2, h3)]
    result = grid_convergence_unequal(*values, h2/h1, h3/h2)
    assert result.observed_order == pytest.approx(2)
    assert result.extrapolated == pytest.approx(2)
    assert result.gci_fine == pytest.approx(1.25 * 0.03 / 2.03)


def test_high_observed_order_cannot_reduce_the_order_capped_estimate():
    # Analytical model f(h)=100+h^4 at h=1,2,4: observed order 4.
    fitted = grid_convergence_unequal(101, 116, 356, 2, 2)
    capped = order_capped_gci(101, 116, 2, fitted.observed_order, 2, 1.25)
    assert fitted.observed_order == pytest.approx(4)
    assert capped == pytest.approx(1.25 * (15 / 101) / 3)
    assert capped > fitted.gci_fine
    assert order_capped_gci(100, 101, 2, 1, 2, 1.25) == pytest.approx(.0125)


@pytest.mark.parametrize('order,cap', [(0, 2), (2, 0), (float('nan'), 2)])
def test_order_cap_requires_explicit_finite_positive_orders(order, cap):
    with pytest.raises(ValueError):
        order_capped_gci(100, 101, 2, order, cap, 1.25)


def test_unequal_mesh_oscillation_and_divergence_are_refused():
    assert grid_convergence_unequal(1, 2, 1, 1.5, 1.4).behaviour == 'oscillatory'
    assert grid_convergence_unequal(1, 2, 2.1, 1.5, 1.4).behaviour == 'divergent'
    with pytest.raises(ValueError):
        grid_convergence_unequal(0, 1, 2, 1.5, 1.4)


def test_conflicting_duplicate_native_history_is_refused(tmp_path):
    import gzip

    from physimesh.postpro.results import _columns
    from physimesh.solver.foam_ascii import FoamAsciiError

    text = gzip.decompress((FIXTURE / 'postProcessing/forces/0/force.dat.gz').read_bytes()).decode()
    lines = text.splitlines()
    tokens = lines[-1].split()
    tokens[1] = str(float(tokens[1]) + 0.1)
    lines[-1] = ' '.join(tokens)
    path = tmp_path / 'force.dat'
    path.write_text('\n'.join(lines)+'\n')
    with pytest.raises(FoamAsciiError, match='conflicting'):
        _columns(path)
