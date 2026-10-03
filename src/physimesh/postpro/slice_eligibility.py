"""Registered visual-slice eligibility; never widens tolerance to fit a dataset."""
import hashlib
import json
from pathlib import Path

import numpy as np

from physimesh.solver.foam_ascii import read_raw_samples

from .plots import resample_slice


def registered_policy() -> tuple[dict, str]:
    raw = Path(__file__).with_name('schema').joinpath('sphere_slice_policy_v1.json').read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def evaluate_slice(samples: np.ndarray, values: np.ndarray, *, diameter_m: float) -> tuple[dict | None, dict]:
    """Return an eligible grid or a refusal with retained sensitivity metrics.

    All grids share bounds, mask and resolution. Changes are normalized by the
    baseline external field span; for a constant baseline the reference is its
    absolute magnitude, with only a floating-point tiny fallback at exact zero.
    Subset coverage is measured against ALL external grid nodes, not just their
    common finite overlap. Geometry violations reject the whole slice.
    """
    policy, digest = registered_policy()
    report = {'policy': policy, 'policy_sha256': digest, 'status': 'refused',
              'maximum_abs_sample_y_m': None, 'sensitivity': [], 'reasons': []}
    samples, values = np.asarray(samples, float), np.asarray(values, float)
    options = {'bounds': tuple(diameter_m*np.asarray(policy['view_bounds_d'])),
               'diameter_m': diameter_m, 'shape': tuple(policy['grid_shape'])}
    tolerance = policy['geometry_tolerance_d']*diameter_m
    try:
        baseline = resample_slice(samples, values, plane_tolerance_m=tolerance, **options)
        report['maximum_abs_sample_y_m'] = float(np.abs(samples[:, 1]).max())
    except ValueError as exc:
        report['reasons'].append(str(exc))
        return None, report
    external = ~baseline['mask']
    finite = np.isfinite(baseline['values']) & external
    coverage = float(finite.sum()/external.sum())
    report['baseline_external_coverage'] = coverage
    if coverage < policy['minimum_external_coverage']:
        report['reasons'].append('baseline slice lacks supported external coverage')
    if not finite.any():
        return None, report
    field = baseline['values'][finite]
    scale = max(float(np.ptp(field)), float(np.max(np.abs(field)))*np.finfo(float).eps,
                np.finfo(float).tiny)
    report['normalization_scale'] = scale
    for fraction in policy['sensitivity_tolerances_d']:
        tolerance = fraction*diameter_m
        keep = np.abs(samples[:, 1]) <= tolerance
        item = {'plane_tolerance_m': tolerance, 'retained_samples': int(keep.sum()), 'passed': False}
        try:
            subset = resample_slice(samples[keep], values[keep], plane_tolerance_m=tolerance, **options)
            overlap = finite & np.isfinite(subset['values'])
            subset_coverage = float((external & np.isfinite(subset['values'])).sum()/external.sum())
            if not overlap.any():
                raise ValueError('no supported common external grid nodes')
            difference = subset['values'][overlap]-baseline['values'][overlap]
            rms = float(np.sqrt(np.mean(difference**2))/scale)
            peak = float(np.max(np.abs(difference))/scale)
            item.update(external_coverage=subset_coverage, normalized_rms_change=rms, normalized_peak_change=peak)
            item['passed'] = (subset_coverage >= policy['minimum_external_coverage']
                              and rms <= policy['maximum_normalized_rms_change']
                              and peak <= policy['maximum_normalized_peak_change'])
        except ValueError as exc:
            item['reason'] = str(exc)
        report['sensitivity'].append(item)
        if not item['passed']:
            report['reasons'].append(f'sensitivity/coverage failed at {fraction:g} D')
    if report['reasons']:
        return None, report
    report['status'] = 'eligible_visualization_only'
    baseline['slice_eligibility'] = report
    return baseline, report


def native_slice_reports(mesh: dict, *, rho: float, diameter_m: float) -> dict:
    """Recompute eligibility from verified native bytes at publication time.

    A copied status or fabricated sensitivity report is insufficient. The full
    report, including exact native-file hashes, must equal this re-derivation.
    """
    case = Path(mesh['case_dir'])
    record_raw = (case/'run_record.json').read_bytes()
    if hashlib.sha256(record_raw).hexdigest() != mesh['run_record_sha256']:
        raise ValueError('slice execution record changed')
    record = json.loads(record_raw)
    reports, coordinates = {}, None
    for field, filename in [('speed', 'U_yNormal.raw'), ('pressure', 'p_yNormal.raw'), ('vorticity', 'vorticity_yNormal.raw')]:
        name = f"postProcessing/cuttingPlane/{mesh['final_time']}/{filename}"
        path = case/name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if record['outputs'].get(name, {}).get('sha256') != digest:
            raise ValueError('native slice source changed')
        _, data = read_raw_samples(path)
        if coordinates is not None and not np.array_equal(coordinates, data[:, :3]):
            raise ValueError('native slice sample associations differ')
        coordinates = data[:, :3]
        values = data[:, 3:6] if field == 'speed' else data[:, 3]*rho if field == 'pressure' else data[:, 4]
        _, reports[field] = evaluate_slice(coordinates, values, diameter_m=diameter_m)
        reports[field]['source_sha256'] = {name: digest}
    return reports


def validate_native_reports(mesh: dict, reports: dict, *, rho: float, diameter_m: float) -> None:
    if reports != native_slice_reports(mesh, rho=rho, diameter_m=diameter_m):
        raise ValueError('slice eligibility differs from independently reprocessed native bytes')
