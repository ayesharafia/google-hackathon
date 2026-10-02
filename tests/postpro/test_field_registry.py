import pytest

from physimesh.postpro.field_registry import DEMO_FIELDS


@pytest.mark.parametrize('field_id', [
    'pressure.static_gauge', 'velocity.magnitude', 'velocity.in_plane', 'vorticity.y',
    'wall_shear.vector', 'wall_shear.magnitude', 'load.cd_history', 'residuals.history',
    'profile.wake_axis_ux', 'mesh_study.cd_by_level',
])
def test_demo_fields_declare_semantics(field_id):
    field = DEMO_FIELDS[field_id]
    assert len(field.dimensions) == 7
    assert all(getattr(field, name) for name in ('association', 'frame', 'derivation', 'units'))
