"""Actual evidence-engine refusals for the stationary laminar sphere demo."""
from dataclasses import asdict

from physimesh.postpro.contour_rules import CapabilityManifest, select_evidence


def sphere_refusals() -> list[dict]:
    # An iteration-drift pass does not establish a physical time-averaging window.
    cap = CapabilityManifest(has_blade_walls=False, has_actuator_sources=False,
                             pressure_kind='kinematic', has_wall_stress=True, velocity_frame='absolute',
                             density_known=True, has_volume_fields=True, has_gradients=True,
                             has_relative_velocity=False, has_yplus=False, turbulent_walls=False,
                             accepted_time_window=False, reference_speed_m_s=1, has_force_history=True)
    output = []
    for request, intent, fields, time_mode, action in (
        ('y_plus', 'numerical_quality', ('y_plus',), 'instantaneous',
         'Use mesh quality and convergence for this laminar case; y+ requires turbulent-wall semantics.'),
        ('mean_pressure', 'body_download', (), 'mean',
         'Use final steady-iteration pressure; physical means need an accepted averaging window.'),
        ('blade_pressure', 'rotor_thrust', ('blade_pressure',), 'instantaneous',
         'Provide blade surfaces and a suitable rotor model; this case is a stationary sphere.'),
        ('independent_ranges', 'body_download', ('independent_ranges',), 'instantaneous',
         'Use shared colour bounds across every compared mesh.'),
    ):
        plan = select_evidence(intent, cap, requested=fields, time_mode=time_mode)
        if not plan.rejected:
            raise ValueError(f'refusal example unexpectedly supported: {request}')
        output.append({'request': request, 'rejected': plan.rejected,
                       'missing': [asdict(item) for item in plan.missing], 'next_action': action})
    return output
