"""Small explicit registry for the verification demo; no inferred field semantics."""
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class FieldDefinition:
    dimensions: tuple[int, ...]
    association: str
    frame: str
    derivation: str
    units: str
    signed: bool = False


DEMO_FIELDS = MappingProxyType({
    'pressure.static_gauge': FieldDefinition((1, -1, -2, 0, 0, 0, 0), 'native face or sampled plane',
        'world', 'native p dimension conversion by declared rho; p_ref=0 Pa', 'Pa', True),
    'velocity.magnitude': FieldDefinition((0, 1, -1, 0, 0, 0, 0), 'sampled plane',
        'absolute world', 'Euclidean norm of native U sample components', 'm/s'),
    'velocity.in_plane': FieldDefinition((0, 1, -1, 0, 0, 0, 0), 'sampled plane',
        'absolute world; y=0 plane', 'native U_x and U_z; interpolate on slice only', 'm/s', True),
    'vorticity.y': FieldDefinition((0, 0, -1, 0, 0, 0, 0), 'sampled plane',
        'world', 'native OpenFOAM vorticity.y = curl(U).y', '1/s', True),
    'wall_shear.vector': FieldDefinition((1, -1, -2, 0, 0, 0, 0), 'native boundary face',
        'world', 'negated native wallShearStress, converted by dimensions to solid traction', 'Pa', True),
    'wall_shear.magnitude': FieldDefinition((1, -1, -2, 0, 0, 0, 0), 'native boundary face',
        'world', 'norm of dimension-converted wall shear vector; not a separation diagnostic', 'Pa'),
    'load.cd_history': FieldDefinition((0, 0, 0, 0, 0, 0, 0), 'integral history',
        'world drag axis +x', 'native forceCoeffs Cd with declared rho,U,D area scale', 'dimensionless', True),
    'residuals.history': FieldDefinition((0, 0, 0, 0, 0, 0, 0), 'solver iteration history',
        'equation components in world axes', 'native solverInfo initial residual for p,Ux,Uy,Uz', 'dimensionless'),
    'profile.wake_axis_ux': FieldDefinition((0, 1, -1, 0, 0, 0, 0), 'sampled line',
        'absolute world', 'centreLine sample recorded p,U order; x,y=z=0', 'm/s', True),
    'mesh_study.cd_by_level': FieldDefinition((0, 0, 0, 0, 0, 0, 0), 'integral per mesh',
        'world drag axis +x', 'reconciled native surface Fx divided by 0.5*rho*U^2*pi*D^2/4', 'dimensionless', True),
})
