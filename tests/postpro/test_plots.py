import numpy as np
import pytest

from physimesh.postpro.plots import render
from physimesh.postpro.recipes import PlotRecipe


def recipe(**kwargs):
    values = {'plot_id': 'pressure', 'field_id': 'pressure.static_gauge', 'kind': 'contour',
                  'run_id': 'captured-sphere', 'source_sha256': 'a'*64,
                  'plane': {'axis': 'y', 'position_m': 0}, 'units': 'Pa', 'colormap': 'RdBu_r',
                  'range_policy': 'shared_global', 'vmin': -3, 'vmax': 3, 'mask': 'sphere interior and nonfinite',
                  'caption': 'VERIFICATION CASE; world frame; final steady iteration; native sample', 'overrides': ()}
    return PlotRecipe(**dict(values, **kwargs))


def test_shared_legend_and_replay_arrays_hash():
    x, z = np.meshgrid(np.linspace(-1, 1, 9), np.linspace(-1, 1, 9))
    data = {'x': x, 'z': z, 'values': x, 'mask': x*x+z*z <= 0.25}
    png, record = render(recipe(), data)
    assert png.startswith(b'\x89PNG')
    assert record['range']['vmin'] == -3 and record['range']['vmax'] == 3
    assert record['arrays_sha256'] == render(recipe(), data)[1]['arrays_sha256']
    altered = dict(data, values=x+1)
    assert render(recipe(run_id='another-mesh'), altered)[1]['range']['vmin'] == -3


def test_masked_values_never_become_zero_and_extrema_reported():
    x, z = np.meshgrid(np.arange(3), np.arange(3))
    v = np.array([[-10, 0, 10], [np.nan, 1, 2], [0, 0, 999]], float)
    mask = np.zeros((3, 3), bool); mask[-1, -1] = True
    _, record = render(recipe(), {'x': x, 'z': z, 'values': v, 'mask': mask})
    assert record['range']['true_min'] == -10
    assert record['range']['true_max'] == 10
    assert record['range']['invalid_count'] == 2
    assert record['range']['clipped_fraction'] == pytest.approx(2/7)
    assert record['mask_color'] == '#9ca9a1'


def test_magnitude_palette_and_signed_zero_center_are_enforced():
    x, z = np.meshgrid(np.arange(3), np.arange(3))
    data = {'x': x, 'z': z, 'values': x}
    with pytest.raises(ValueError, match='zero'):
        render(recipe(vmin=-1, vmax=3), data)
    with pytest.raises(ValueError, match='viridis'):
        render(recipe(field_id='velocity.magnitude', units='m/s'), data)


def test_slice_resampling_and_streamline_mask():
    from physimesh.postpro.plots import resample_slice

    x, z = np.meshgrid(np.linspace(-1, 1, 7), np.linspace(-1, 1, 7))
    coords = np.c_[x.ravel(), np.zeros(x.size), z.ravel()]
    velocity = np.tile([1., 0., 0.], (x.size, 1))
    data = resample_slice(coords, velocity, bounds=(-1, 1, -1, 1), diameter_m=1, shape=(21, 21))
    assert data['mask'][10, 10]
    png, record = render(recipe(field_id='velocity.in_plane', units='m/s', kind='streamlines',
                                colormap='viridis', vmin=0, vmax=2), data)
    assert png.startswith(b'\x89PNG')
    assert record['range']['invalid_count'] > 0
