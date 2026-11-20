"""Recipe-driven static plots; visual interpolation is never used for loads."""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import textwrap
from dataclasses import asdict
from pathlib import Path

import matplotlib
import scipy

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize, TwoSlopeNorm

from physimesh.postpro.contour_rules import RangeRecord
from physimesh.postpro.field_registry import DEMO_FIELDS
from physimesh.postpro.recipes import PlotRecipe

MASK_COLOR = '#9ca9a1'


def arrays_hash(data: dict) -> str:
    """Hash names, shapes, dtypes and bytes; canonical metadata for nonarrays."""
    digest = hashlib.sha256()
    for key in sorted(data):
        value = data[key]
        digest.update(key.encode()+b'\0')
        if isinstance(value, np.ndarray):
            array = np.ascontiguousarray(value)
            digest.update(str(array.shape).encode()+array.dtype.str.encode()+array.tobytes())
        else:
            digest.update(json.dumps(value, sort_keys=True, allow_nan=False).encode())
    return digest.hexdigest()


def _range(recipe, values, mask):
    valid = np.isfinite(values) & ~mask
    if not valid.any():
        raise ValueError('plot has no unmasked finite samples')
    minimum, maximum = float(values[valid].min()), float(values[valid].max())
    if recipe.range_policy not in ('shared_global', 'shared_temporal', 'single_full_range'):
        raise ValueError('unsupported range policy')
    if recipe.range_policy != 'single_full_range' and (recipe.vmin is None or recipe.vmax is None):
        raise ValueError('shared plots need precomputed bounds across all compared runs')
    lo = minimum if recipe.vmin is None else recipe.vmin
    hi = maximum if recipe.vmax is None else recipe.vmax
    if not all(math.isfinite(x) for x in (lo, hi)) or lo > hi:
        raise ValueError('invalid plot range')
    # A constant field still displays as a constant, never through division by 0.
    if lo == hi:
        delta = max(abs(lo)*1e-6, 1e-12)
        lo, hi = lo-delta, hi+delta
    fraction = float(((values[valid] < lo) | (values[valid] > hi)).mean())
    return RangeRecord(recipe.range_policy, float(lo), float(hi), minimum, maximum,
                       fraction, False, int((~valid).sum()))


def render(recipe: PlotRecipe, data: dict) -> tuple[bytes, dict]:
    """Regular-grid contours/vectors/streamlines or declared XY/bar series.

    Masked/non-finite samples stay masked and grey. No PNG-byte replay claim;
    the array hash and full serialized recipe are the reproducibility contract.
    """
    if recipe.renderer_version != 'native_plot_v1':
        raise ValueError('unsupported renderer version')
    field = DEMO_FIELDS[recipe.field_id]
    if recipe.units != field.units:
        raise ValueError('recipe units differ from declared field semantics')
    if re.fullmatch(r'[0-9a-f]{64}', recipe.source_sha256) is None:
        raise ValueError('recipe requires source SHA-256')
    if 'VERIFICATION CASE' not in recipe.caption:
        raise ValueError('verification plots require an explicit case label')
    if recipe.kind not in ('contour', 'vectors', 'streamlines', 'xy', 'bar'):
        raise ValueError('unsupported plot kind')
    values = np.asarray(data['values'], float)
    mask = np.asarray(data.get('mask', np.zeros(values.shape, bool)), bool)
    if values.shape != mask.shape:
        raise ValueError('mask shape mismatch')
    record = _range(recipe, values, mask)
    masked = np.ma.array(values, mask=mask | ~np.isfinite(values))
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=130)
    fig.patch.set_facecolor('#edf2ed'); ax.set_facecolor(MASK_COLOR if recipe.kind in ('contour', 'vectors', 'streamlines') else '#edf2ed')
    try:
        if recipe.kind in ('contour', 'vectors', 'streamlines'):
            if field.signed and recipe.kind == 'contour':
                if not record.vmin < 0 < record.vmax or not math.isclose(-record.vmin, record.vmax):
                    raise ValueError('signed contour range must be centered at zero')
                if recipe.colormap != 'RdBu_r':
                    raise ValueError('signed contours require diverging RdBu_r')
                norm = TwoSlopeNorm(0, vmin=record.vmin, vmax=record.vmax)
            else:
                if recipe.colormap != 'viridis':
                    raise ValueError('magnitude contours require viridis')
                norm = Normalize(record.vmin, record.vmax)
            cmap = plt.get_cmap(recipe.colormap).with_extremes(bad=MASK_COLOR)
            x, z = np.asarray(data['x'], float), np.asarray(data['z'], float)
            if x.shape != values.shape or z.shape != values.shape:
                raise ValueError('slice grid shape mismatch')
            artist = ax.pcolormesh(x, z, masked, shading='auto', cmap=cmap, norm=norm, rasterized=True)
            if recipe.kind in ('vectors', 'streamlines'):
                u, w = np.asarray(data['u'], float), np.asarray(data['w'], float)
                if u.shape != values.shape or w.shape != values.shape:
                    raise ValueError('in-plane vector shape mismatch')
                vector_mask = np.ma.getmaskarray(masked) | ~np.isfinite(u) | ~np.isfinite(w)
                u, w = np.ma.array(u, mask=vector_mask), np.ma.array(w, mask=vector_mask)
                if recipe.kind == 'vectors':
                    step = max(1, values.shape[1]//28)
                    ax.quiver(x[::step, ::step], z[::step, ::step], u[::step, ::step], w[::step, ::step],
                              color='#203c2c', pivot='mid')
                else:
                    ax.streamplot(x[0], z[:, 0], u, w, color='#203c2c', density=1.1, linewidth=0.7)
            color_label = (f'|U| [{recipe.units}]; vectors Ux,Uz' if recipe.kind in ('vectors', 'streamlines')
                           else f'{recipe.field_id} [{recipe.units}]')
            fig.colorbar(artist, ax=ax, label=color_label, pad=0.025)
            ax.set(xlabel='world x [m]', ylabel='world z [m]', aspect='equal')
        elif recipe.kind == 'xy':
            x = np.asarray(data['x'], float)
            series = masked[None, :] if masked.ndim == 1 else masked
            if series.shape[-1] != x.size or not np.isfinite(x).all():
                raise ValueError('XY coordinate mismatch')
            labels = data['labels']
            if len(labels) != len(series):
                raise ValueError('XY labels mismatch')
            for index, (label, y) in enumerate(zip(labels, series, strict=True)):
                ax.plot(x, y, label=label, color=('#23402f', '#687d6e', '#ad6955', '#556578')[index % 4])
            if data.get('log_y'):
                if np.any(masked.compressed() <= 0):
                    raise ValueError('log residual plot requires positive samples')
                ax.set_yscale('log')
            ax.set(xlabel=data['x_label'], ylabel=f'{recipe.field_id} [{recipe.units}]')
            ax.legend(frameon=False)
        else:
            ax.bar(data['labels'], masked, color='#5d7967', width=0.55)
            if data.get('reference') is not None:
                ax.axhline(data['reference'], color='#9c5e48', linestyle=':', label='Schiller–Naumann reference')
                ax.legend(frameon=False)
            if data.get('gci_absolute') is not None:
                ax.errorbar(len(values)-1, values[-1], yerr=data['gci_absolute'], color='#203c2c', capsize=5)
            ax.set(ylabel=f'{recipe.field_id} [{recipe.units}]')
        ax.set_title(recipe.plot_id.replace('_', ' '), loc='left', fontsize=14)
        for spine in ('top', 'right'):
            ax.spines[spine].set_visible(False)
        caption = (f'{recipe.caption} | run {recipe.run_id} | {recipe.field_id} [{recipe.units}] | '
                   f'range {record.vmin:.5g} to {record.vmax:.5g}; '
                   f'true extrema {record.true_min:.5g} to {record.true_max:.5g}; '
                   f'clipped {record.clipped_fraction:.2%}; invalid/masked {record.invalid_count}.')
        fig.subplots_adjust(bottom=0.25, top=0.89, left=0.10, right=0.92)
        fig.text(0.06, 0.03, '\n'.join(textwrap.wrap(caption, 120)), fontsize=8, color='#203c2c', va='bottom')
        stream = io.BytesIO(); fig.savefig(stream, format='png')
        return stream.getvalue(), {'range': asdict(record), 'arrays_sha256': arrays_hash(data),
                                  'operators': {'renderer': recipe.renderer_version, 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                                'matplotlib': matplotlib.__version__, 'numpy': np.__version__, 'scipy': scipy.__version__,
                                                'figure_inches': [10, 6.5], 'dpi': 130, 'shading': 'auto',
                                                'vector_stride': max(1, values.shape[-1]//28), 'streamline_density': 1.1,
                                                'interpolation': data.get('interpolation')},
                                  'mask_color': MASK_COLOR, 'caption': caption, 'recipe': asdict(recipe)}
    finally:
        plt.close(fig)


def resample_slice(samples: np.ndarray, values: np.ndarray, *, bounds: tuple[float, float, float, float],
                   diameter_m: float, plane_tolerance_m: float = 1e-10, shape: tuple[int, int] = (180, 360)) -> dict:
    """Linear griddata on native y=0 samples; grey outside hull or sphere interior.

    This regular grid is a visual interpolation only. It must never replace
    unsmoothed native face data for integration. Coordinates are world x and z.
    """
    from scipy.interpolate import griddata
    from scipy.spatial import QhullError

    samples, values = np.asarray(samples, float), np.asarray(values, float)
    if (samples.ndim != 2 or samples.shape[1] != 3 or len(values) != len(samples)
            or not np.isfinite(samples).all() or not np.isfinite(values).all()):
        raise ValueError('finite native slice coordinates and matching values required')
    if not math.isfinite(plane_tolerance_m) or plane_tolerance_m < 0:
        raise ValueError('explicit finite nonnegative plane tolerance required')
    if not np.allclose(samples[:, 1], 0, atol=plane_tolerance_m, rtol=0):
        raise ValueError('demo requires explicitly y=0 world slice')
    if diameter_m <= 0 or not math.isfinite(diameter_m) or min(shape) < 2:
        raise ValueError('positive diameter and valid grid shape required')
    xmin, xmax, zmin, zmax = bounds
    if not all(math.isfinite(v) for v in bounds) or xmin >= xmax or zmin >= zmax:
        raise ValueError('invalid view bounds')
    x, z = np.meshgrid(np.linspace(xmin, xmax, shape[1]), np.linspace(zmin, zmax, shape[0]))
    if len(samples) < 3:
        raise ValueError('slice requires at least three non-collinear samples')
    try:
        grid = griddata(samples[:, [0, 2]], values, (x, z), method='linear')
    except QhullError as exc:
        raise ValueError('slice lacks supported two-dimensional sample geometry') from exc
    interior = x*x+z*z <= (diameter_m/2)**2
    result = {'x': x, 'z': z, 'values': grid, 'mask': interior, 'interpolation': {'version': 'slice_griddata_v1', 'method': 'linear', 'shape': list(shape),
                                                    'bounds_m': list(bounds), 'diameter_m': diameter_m, 'plane_tolerance_m': plane_tolerance_m}}
    if grid.ndim == 3:
        if grid.shape[-1] != 3:
            raise ValueError('vector slice must contain world Ux,Uy,Uz')
        result.update(u=grid[:, :, 0], w=grid[:, :, 2], vector_world=grid, values=np.linalg.norm(grid, axis=-1))
    return result
