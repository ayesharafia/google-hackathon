"""Verification results from unsmoothed native evidence [M§16; MVP D2.2]."""
from __future__ import annotations

import gzip
import hashlib
import math
from dataclasses import asdict
from pathlib import Path

import numpy as np

from physimesh.postpro.loads3d import (
    integrate_surface_loads,
    reconcile,
    solid_area_vectors_from_backend,
    to_physical_pressure,
    to_physical_stress,
)
from physimesh.postpro.statistics import drift, window_stats
from physimesh.solver.foam_ascii import (
    FoamAsciiError,
    face_centres_and_areas,
    read_boundary,
    read_faces,
    read_function_object_table,
    read_patch_field,
    read_points,
)


def _columns(path: Path):
    names, rows = read_function_object_table(path)
    # v2606 writes an identical final row again on end(). Collapse exact
    # adjacent duplicates only; conflicting values at one iteration are refused.
    keep = np.ones(len(rows), dtype=bool)
    for i in range(1, len(rows)):
        if rows[i, 0] == rows[i-1, 0]:
            if not np.array_equal(rows[i], rows[i-1]):
                raise FoamAsciiError('conflicting native values at duplicate iteration')
            keep[i] = False
    rows = rows[keep]
    try:
        values = {name: np.asarray(rows[:, i], float) for i, name in enumerate(names)}
    except ValueError as exc:
        raise FoamAsciiError('non-numeric force or coefficient output') from exc
    if not np.isfinite(rows.astype(float)).all():
        raise FoamAsciiError('non-finite load table')
    times = values.get('Time')
    if times is None or np.any(np.diff(times) <= 0):
        raise FoamAsciiError('load history needs strictly increasing native iterations')
    return values


def _vector(columns, prefix, index):
    return np.array([columns[f'{prefix}_{axis}'][index] for axis in 'xyz'])


def _source(path):
    actual = path if path.exists() else path.with_name(path.name + '.gz')
    raw = actual.read_bytes()
    if actual.suffix == '.gz':
        raw = gzip.decompress(raw)
    return hashlib.sha256(raw).hexdigest()


def sphere_load_result(case_dir: Path, final_time: str, *, rho: float,
                       speed: float, diameter: float) -> dict:
    """Origin-centred stationary sphere, x-directed flow; no aircraft claim.

    OpenCFD v2606 wallShearStress is traction with the fluid-domain normal.
    Negate it once after dimensional conversion to obtain traction on solid.
    This adapter convention was measured against native pressure/viscous forces.
    """
    if not all(math.isfinite(x) and x > 0 for x in (rho, speed, diameter)):
        raise ValueError('explicit positive finite density, speed and diameter required')
    case_dir = Path(case_dir)
    mesh = case_dir / 'constant/polyMesh'
    patch = read_boundary(mesh / 'boundary')['sphere']
    all_faces = read_faces(mesh / 'faces')
    start, count = patch['startFace'], patch['nFaces']
    if count <= 0 or start+count > len(all_faces):
        raise FoamAsciiError('invalid sphere patch addressing')
    centres, sf_fluid = face_centres_and_areas(read_points(mesh / 'points'), all_faces[start:start+count])
    p, p_dims = read_patch_field(case_dir / final_time / 'p', 'sphere')
    wss, wss_dims = read_patch_field(case_dir / final_time / 'wallShearStress', 'sphere')
    if p.shape != (count,) or wss.shape != (count, 3):
        raise FoamAsciiError('sphere pressure/shear field rank mismatch')
    loads = integrate_surface_loads(centres, solid_area_vectors_from_backend(sf_fluid),
                                   to_physical_pressure(p, p_dims, field_name='p', rho=rho),
                                   -to_physical_stress(wss, wss_dims, rho=rho), [0, 0, 0], 0)
    force_path = case_dir / 'postProcessing/forces/0/force.dat'
    moment_path = case_dir / 'postProcessing/forces/0/moment.dat'
    coeff_path = case_dir / 'postProcessing/forceCoeffs1/0/coefficient.dat'
    force, moment, coeff = (_columns(path) for path in (force_path, moment_path, coeff_path))
    indices = []
    for table in (force, moment, coeff):
        matches = np.flatnonzero(table['Time'] == float(final_time))
        if len(matches) != 1:
            raise FoamAsciiError('final field iteration absent or ambiguous in native loads')
        indices.append(matches[0])
    force_index, moment_index, coeff_index = indices
    scale = 0.5*rho*speed**2 * math.pi*diameter**2/4
    cd = float(loads.force_total_n[0]/scale)
    checks = {}
    for name, ours, native in (
        ('pressure', loads.force_pressure_n, _vector(force, 'pressure', force_index)),
        ('viscous', loads.force_viscous_n, _vector(force, 'viscous', force_index)),
        ('total', loads.force_total_n, _vector(force, 'total', force_index)),
        ('moment', loads.moment_total_nm, _vector(moment, 'total', moment_index)),
        ('cd', np.array([cd]), np.array([coeff['Cd'][coeff_index]])),
    ):
        check = reconcile(ours, native, rel_tol=1e-3, abs_tol=1e-6)
        checks[name] = {'passed': check.passed, 'ours': ours.tolist(), 'native': native.tolist(),
                        'absolute_error': check.abs_error.tolist(), 'allowed': check.allowed.tolist()}
    accepted = all(check['passed'] for check in checks.values())
    end = float(final_time)
    windows = [window_stats(coeff['Time'], coeff['Cd'], end-400, end-200),
               window_stats(coeff['Time'], coeff['Cd'], end-200, end)]
    # A truncated history must never masquerade as two complete windows.
    if (windows[0].t_start != end-400 or windows[-1].t_end != end
            or any(window.n_samples != 201 for window in windows)):
        raise FoamAsciiError('two complete 200-iteration windows required')
    cd_drift = drift(windows, abs_scale=1e-6)
    reference = 1.09173  # frozen plan value; no tuning to the correlation
    source_paths = [mesh/'points', mesh/'faces', mesh/'boundary', mesh/'owner',
                    case_dir/final_time/'p', case_dir/final_time/'wallShearStress',
                    force_path, moment_path, coeff_path]
    return {
        'final_iteration': end, 'evidence': 'unverified', 'label': 'VERIFICATION CASE: sphere Re=100',
        'force_pressure_n': loads.force_pressure_n.tolist(),
        'force_viscous_n': loads.force_viscous_n.tolist(), 'force_total_n': loads.force_total_n.tolist(),
        'moment_total_nm': loads.moment_total_nm.tolist(), 'moment_origin_m': [0, 0, 0],
        'surface_area_m2': loads.area_m2, 'cd': cd,
        'reference_cd': reference, 'reference_relative_difference': (cd-reference)/reference,
        'reconciliation': {'status': 'accepted' if accepted else 'diagnostic_only',
                           'relative_tolerance': 1e-3, 'absolute_tolerance': 1e-6, 'checks': checks},
        'convergence': {'passed': bool(cd_drift < 0.005), 'drift': float(cd_drift), 'threshold': 0.005,
                        'treatment': 'steady iteration windows, not physical time averages',
                        'windows': [asdict(window) for window in windows]},
        'source_sha256': {str(path.relative_to(case_dir)): _source(path) for path in source_paths},
        'conventions': {'pressure': 'native dimensions; kinematic multiplied by declared rho once',
                        'wall_shear': 'negate native fluid-normal traction once for force on solid',
                        'normal': 'negate native fluid-domain Sf once', 'p_ref_pa': 0,
                        'history_duplicates': 'collapse byte-value-identical adjacent rows; conflicts refused'},
    }
