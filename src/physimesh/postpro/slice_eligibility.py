"""Registered visual-slice eligibility; never widens tolerance to fit a dataset."""
import hashlib
import json
from pathlib import Path

import numpy as np

from physimesh.solver.foam_ascii import read_raw_samples

from .plots import resample_slice

POLICY_PATH = Path(__file__).with_name('schema').joinpath('sphere_slice_policy_v1.json')
POLICY_DIGESTS = {'sphere_slice_policy_v1': 'babdcdb91ee800086d4aeb4a32d6dfae6e2d1614b668f906e517ba86f02213a7'}
REGISTRATION_INPUT = 'system/sliceEligibility.json'


def registered_policy() -> tuple[dict, str]:
    raw = POLICY_PATH.read_bytes()
    policy, digest = json.loads(raw), hashlib.sha256(raw).hexdigest()
    if POLICY_DIGESTS.get(policy['schema_version']) != digest:
        raise ValueError('registered slice policy changed under its version; register a new version')
    return policy, digest


def registration_input() -> bytes:
    policy, digest = registered_policy()
    return (json.dumps({'schema_version': 'slice_policy_registration_v1',
                        'policy_version': policy['schema_version'], 'policy_sha256': digest}, sort_keys=True)+'\n').encode()


def registration_for_run(case: Path, record: dict) -> dict:
    """A pre-execution input hash, not a retroactive annotation, proves binding."""
    if REGISTRATION_INPUT not in record.get('inputs', {}):
        return {'state': 'retrospective', 'reason': 'captured native run predates registered policy input'}
    raw = (case/REGISTRATION_INPUT).read_bytes()
    if raw != registration_input() or hashlib.sha256(raw).hexdigest() != record['inputs'][REGISTRATION_INPUT]:
        raise ValueError('pre-execution slice registration differs from the registered policy')
    return {'state': 'pre_execution_input', 'input_path': REGISTRATION_INPUT,
            'input_sha256': hashlib.sha256(raw).hexdigest(), **json.loads(raw)}


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
              'maximum_abs_sample_y_m': None, 'sensitivity': [], 'reasons': [],
              'registration': {'state': 'evaluation_only', 'reason': 'no native run input binding supplied'}}
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
    # Velocity eligibility covers its direction as well as speed. A norm-only
    # comparison could approve a complete reversal for vector/streamline views.
    vector = 'vector_world' in baseline
    field = baseline['vector_world'][finite] if vector else baseline['values'][finite]
    span = float(np.linalg.norm(np.ptp(field, axis=0))) if vector else float(np.ptp(field))
    magnitude = float(np.max(np.linalg.norm(field, axis=-1))) if vector else float(np.max(np.abs(field)))
    scale = span if span > 64*np.finfo(float).eps*magnitude else max(magnitude, np.finfo(float).tiny)
    report['normalization_scale'] = scale
    report['compared_quantity'] = 'world_velocity_vector' if vector else 'scalar_field'
    report['normalization'] = 'field span (Euclidean component-span norm for vectors); constant-field magnitude fallback'
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
            difference = (np.linalg.norm(subset['vector_world'][overlap]-baseline['vector_world'][overlap], axis=-1)
                          if vector else subset['values'][overlap]-baseline['values'][overlap])
            rms = float(np.sqrt(np.mean(difference**2))/scale)
            peak = float(np.max(np.abs(difference))/scale)
            item.update(external_coverage=subset_coverage, normalized_rms_change=rms, normalized_peak_change=peak)
            failures = []
            if subset_coverage < policy['minimum_external_coverage']:
                failures.append('external coverage')
            if rms > policy['maximum_normalized_rms_change']:
                failures.append('normalized RMS change')
            if peak > policy['maximum_normalized_peak_change']:
                failures.append('normalized peak change')
            item['failed_metrics'] = failures
            item['passed'] = not failures
        except ValueError as exc:
            item['reason'] = str(exc)
        report['sensitivity'].append(item)
        if not item['passed']:
            detail = ', '.join(item.get('failed_metrics', [])) or item.get('reason', 'unsupported subset')
            report['reasons'].append(f'{detail} failed at {fraction:g} D')
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
    registration = registration_for_run(case, record)
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
        reports[field]['registration'] = registration
    return reports


def validate_native_reports(mesh: dict, reports: dict, *, rho: float, diameter_m: float) -> None:
    if reports != native_slice_reports(mesh, rho=rho, diameter_m=diameter_m):
        raise ValueError('slice eligibility differs from independently reprocessed native bytes')
