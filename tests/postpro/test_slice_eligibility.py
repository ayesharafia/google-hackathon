import numpy as np
import pytest

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
    assert digest == '8744e2b764df40d4975b0cafc31c2dd7462099643f83a8b91eea69080abdd5b1'
    policy['maximum_normalized_peak_change'] = .06
    changed = tmp_path/'policy.json'
    changed.write_text(json.dumps(policy))
    monkeypatch.setattr(module, 'POLICY_PATH', changed)
    with pytest.raises(ValueError, match='changed under its version'):
        registered_policy()


@pytest.mark.parametrize('version', ['sphere_slice_policy_v1', 'sphere_slice_policy_v2', 'sphere_slice_policy_v3'])
@pytest.mark.parametrize('vector', [True, False])
def test_known_reversal_metric_is_retained_per_policy_version(version, vector):
    # Nested triangles avoid coincident x/z samples and ambiguous Qhull tie-breaking.
    # The whole view is inside the inner off-plane triangle: baseline = -a,
    # tighter subsets = +a. Span is zero, magnitude fallback = a, hence RMS = peak = 2.
    on_plane = np.array([[-100, 0, -100], [100, 0, -100], [0, 0, 100]], float)
    off_plane = on_plane/10
    off_plane[:, 1] = 8e-6
    samples = np.concatenate([off_plane, on_plane])
    values = np.array([[-1, 0, 0]]*3+[[1, 0, 0]]*3, float) if vector else np.array([-3]*3+[3]*3)
    grid, report = evaluate_slice(samples, values, diameter_m=1, policy_version=version)
    assert grid is None and report['status'] == 'refused'
    assert report['compared_quantity'] == ('world_velocity_vector' if vector else 'scalar_field')
    assert report['normalization_scale'] == pytest.approx(1 if vector else 3, abs=1e-14)
    assert all(item['external_coverage'] == 1 for item in report['sensitivity'])
    for item in report['sensitivity']:
        assert item['normalized_peak_change'] == pytest.approx(2, abs=1e-14)
        assert item['normalized_rms_change'] == pytest.approx(2, abs=1e-14)
    if version == 'sphere_slice_policy_v3':
        import scipy
        assert report['operator_versions']['scipy'] == scipy.__version__


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


def test_v1_bytes_preserved_and_v2_binds_full_metric_without_looser_limits():
    old, old_sha = registered_policy('sphere_slice_policy_v1')
    new, new_sha = registered_policy('sphere_slice_policy_v2')
    assert old_sha == 'babdcdb91ee800086d4aeb4a32d6dfae6e2d1614b668f906e517ba86f02213a7'
    assert new_sha != old_sha
    assert new['metric_definition']['velocity_quantity'] == 'world_velocity_vector'
    assert new['metric_definition']['nonfinite'] == 'refuse'
    assert {k: v for k, v in new.items() if k not in ('schema_version', 'metric_definition')} == {
        k: v for k, v in old.items() if k != 'schema_version'}


def test_v3_retains_v2_bytes_and_limits_and_defines_exact_grid_and_comparison_sets():
    old, digest = registered_policy('sphere_slice_policy_v2')
    new, _ = registered_policy('sphere_slice_policy_v3')
    assert digest == '94a3a59109753b79556a74424bbac14a759e814faa3df2a756c2c2418bc85a0f'
    assert {k: v for k, v in new.items() if k not in ('schema_version', 'metric_definition')} == {
        k: v for k, v in old.items() if k not in ('schema_version', 'metric_definition')}
    assert new['metric_definition']['comparison_nodes'] == 'external_grid_nodes_finite_in_both_baseline_and_subset'
    assert new['metric_definition']['grid_axes'] == 'rows_world_z_columns_world_x'
