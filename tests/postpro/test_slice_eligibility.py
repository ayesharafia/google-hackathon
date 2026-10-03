import numpy as np

from physimesh.postpro.slice_eligibility import evaluate_slice, registered_policy


def points():
    x, z = np.meshgrid(np.linspace(-2, 5, 12), np.linspace(-2, 2, 10))
    return np.c_[x.ravel(), np.zeros(x.size), z.ravel()]


def test_supported_plane_has_fixed_policy_and_stable_subset_evidence():
    xyz = points()
    grid, check = evaluate_slice(xyz, xyz[:, 0]+2*xyz[:, 2], diameter_m=1)
    assert grid is not None and check['status'] == 'eligible_visualization_only'
    assert all(item['passed'] for item in check['sensitivity'])
    assert all(item['normalized_peak_change'] == 0 for item in check['sensitivity'])
    assert len(check['policy_sha256']) == 64


def test_geometry_tolerance_cannot_widen_to_fit_captured_points():
    xyz = points()
    xyz[5, 1] = 1.01e-5
    grid, check = evaluate_slice(xyz, np.ones(len(xyz)), diameter_m=1)
    assert grid is None and check['status'] == 'refused'
    assert registered_policy()[0]['geometry_tolerance_d'] == 1e-5


def test_missing_view_coverage_is_not_hidden_by_common_overlap():
    xyz = points()
    xyz = xyz[xyz[:, 0] < 0]
    grid, check = evaluate_slice(xyz, np.ones(len(xyz)), diameter_m=1)
    assert grid is None and check['baseline_external_coverage'] < .99


def test_off_plane_outlier_changes_view_and_is_refused():
    xyz = points()
    values = xyz[:, 0]+2*xyz[:, 2]
    xyz[50, 1] = 8e-6
    values[50] = 1000
    grid, check = evaluate_slice(xyz, values, diameter_m=1)
    assert grid is None and any(not item['passed'] for item in check['sensitivity'])


def test_degenerate_sample_geometry_is_refused():
    xyz = np.c_[np.linspace(-2, 5, 10), np.zeros(10), np.zeros(10)]
    grid, check = evaluate_slice(xyz, np.ones(10), diameter_m=1)
    assert grid is None and check['reasons']


def test_policy_version_is_pinned_and_cannot_silently_admit_more_views(tmp_path, monkeypatch):
    import json

    import pytest

    import physimesh.postpro.slice_eligibility as module
    policy, digest = registered_policy()
    assert digest == 'babdcdb91ee800086d4aeb4a32d6dfae6e2d1614b668f906e517ba86f02213a7'
    policy['maximum_normalized_peak_change'] = .06
    changed = tmp_path/'policy.json'
    changed.write_text(json.dumps(policy))
    monkeypatch.setattr(module, 'POLICY_PATH', changed)
    with pytest.raises(ValueError, match='changed under its version'):
        registered_policy()


def test_velocity_reversal_cannot_hide_behind_identical_speed():
    on_plane = np.array([[-100, 0, -100], [100, 0, -100], [0, 0, 100]], float)
    off_plane = on_plane.copy()
    off_plane[:, 1] = 8e-6
    samples = np.concatenate([off_plane, on_plane])
    velocity = np.array([[-1, 0, 0]]*3+[[1, 0, 0]]*3, float)
    grid, report = evaluate_slice(samples, velocity, diameter_m=1)
    assert grid is None and report['status'] == 'refused'
    assert report['compared_quantity'] == 'world_velocity_vector'
    assert all(item['external_coverage'] == 1 for item in report['sensitivity'])
    assert all(item['normalized_peak_change'] > .05 for item in report['sensitivity'])


def test_extreme_finite_velocity_refuses_overflow_without_nonfinite_report():
    import json

    on_plane = np.array([[-1.5, 0, -1.5], [4, 0, -1.5], [-1.5, 0, 1.5], [4, 0, 1.5]])
    off_plane = on_plane.copy()
    off_plane[:, 1] = 8e-6
    velocities = np.c_[np.where(on_plane[:, 0] < 0, -1e154, 1e154), np.zeros((4, 2))]
    grid, report = evaluate_slice(np.concatenate([off_plane, on_plane]),
                                  np.concatenate([velocities, -velocities]), diameter_m=1)
    assert grid is None and report['status'] == 'refused'
    assert report['reasons'] == ['nonfinite sensitivity normalization']
    json.dumps(report, allow_nan=False)
