"""Versioned measured-curve conditioning; raw samples are never rewritten.

Power bounds the declared upper sample envelope, not unknown installed performance.
Torque error is an independent per-rotor interval, checked on all moment axes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import Field
from scipy.optimize import linprog

from physimesh.projects.contracts import Record

from .performance import RotorMapV1
from .provenance import sha256_record


class ConditioningPolicyV1(Record):
    schema_version: Literal['rotor_conditioning_policy_v1']
    source_note: str = Field(min_length=1, max_length=2000)
    torque_relative_residual_tolerance: float = Field(ge=0, le=1)
    power_relative_uncertainty: float = Field(ge=0, lt=1)
    torque_relative_uncertainty: float = Field(ge=0, lt=1)
    max_power_shift_fraction: float = Field(ge=0, le=1)


class ConditionedProfileV1(Record):
    schema_version: Literal['conditioned_rotor_profile_v1']
    policy: ConditioningPolicyV1
    thrust_n: tuple[float, ...] = Field(min_length=2, max_length=64)
    rpm: tuple[float, ...] = Field(min_length=2, max_length=64)
    electrical_power_w: tuple[float, ...]
    sample_upper_electrical_power_w: tuple[float, ...]
    power_shift_w: float = Field(ge=0)
    torque_slope_nm_per_n: float = Field(ge=0)
    torque_offset_nm: float
    torque_max_relative_residual: float = Field(ge=0)
    torque_error_bound_nm: float = Field(ge=0)
    qualification: str


def upper_envelope(x, target):
    hull = []
    for i in range(len(x)):
        while len(hull) >= 2:
            a, b = hull[-2:]
            if (target[b]-target[a])/(x[b]-x[a]) <= (target[i]-target[b])/(x[i]-x[b]):
                break
            hull.pop()
        hull.append(i)
    lower = np.interp(x, x[hull], target[hull])
    shift = float(np.max(target-lower))
    return lower+shift, shift


def validate_retained_profile(model, profile):
    """Check retained coefficients without re-fitting them with a future solver."""
    from .provenance import canonical_json
    p = ConditionedProfileV1.model_validate_json(canonical_json(profile))
    x = np.array(p.thrust_n); rpm = np.array(p.rpm)
    if (p.thrust_n != tuple(point.thrust_n for point in model.points)
            or p.rpm != tuple(point.rpm for point in model.points)
            or np.any(np.diff(x) <= 0)
            or model.covered_intervals_rpm != ((model.points[0].rpm, model.points[-1].rpm),)):
        raise ValueError('conditioned coordinates or coverage differ from the retained raw source')
    q = np.array([point.shaft_torque_nm for point in model.points])
    fitted = p.torque_slope_nm_per_n*x+p.torque_offset_nm
    residual = np.abs(fitted-q)
    relative = float(np.max(np.divide(residual, q, out=np.zeros_like(q), where=q > 0)))
    policy = p.policy
    band = float(np.max(residual+q*policy.torque_relative_uncertainty/(1-policy.torque_relative_uncertainty)))
    efficiency = model.efficiency if model.power_basis == 'shaft' else 1.
    target = np.maximum(np.array([point.power_w for point in model.points])/efficiency/(
        1-policy.power_relative_uncertainty), (fitted+p.torque_error_bound_nm)*rpm*2*np.pi/60/efficiency)
    power, shift = upper_envelope(x, target)
    if (not policy.source_note.strip() or np.any(fitted < -1e-10)
            or np.any((q == 0) & (residual > 1e-10))
            or relative > policy.torque_relative_residual_tolerance+1e-10
            or abs(relative-p.torque_max_relative_residual) > 1e-10
            or p.torque_error_bound_nm+1e-10 < band
            or shift > policy.max_power_shift_fraction*max(float(np.max(target)), 1e-12)+1e-10
            or abs(shift-p.power_shift_w) > 1e-8
            or not np.allclose(p.sample_upper_electrical_power_w, target, rtol=1e-10, atol=1e-9)
            or not np.allclose(p.electrical_power_w, power, rtol=1e-10, atol=1e-9)
            or np.any(np.diff(power)/np.diff(x) < -1e-10)):
        raise ValueError('retained conditioned profile fails its versioned sample-envelope policy')
    return p.model_dump(mode='json')


def condition_map(model: RotorMapV1, policy: ConditioningPolicyV1) -> dict:
    if not policy.source_note.strip():
        raise ValueError('conditioning policy needs a meaningful source')
    x = np.array([p.thrust_n for p in model.points])
    q = np.array([p.shaft_torque_nm for p in model.points])
    rpm = np.array([p.rpm for p in model.points])
    if (np.any(np.diff(x) <= 0) or len(model.covered_intervals_rpm) != 1
            or model.covered_intervals_rpm[0] != (model.points[0].rpm, model.points[-1].rpm)):
        raise ValueError('conditioning requires increasing thrust and one full explicitly covered RPM interval')
    # Minimax relative-residual fit, with nonnegative slope and endpoint torque.
    # A zero measured torque is constrained exactly; it has no relative allowance.
    weights = q.copy()
    rows = np.vstack((np.column_stack((x, np.ones(len(x)), -weights)),
                      np.column_stack((-x, -np.ones(len(x)), -weights)),
                      [-x[0], -1, 0]))
    upper = np.concatenate((q, -q, [0]))
    fit = linprog([0., 0., 1.], A_ub=rows, b_ub=upper,
                  bounds=[(0, None), (None, None), (0, None)], method='highs',
                  options={'time_limit': 1., 'maxiter': 10000})
    if not fit.success or fit.x is None or not np.isfinite(fit.x).all():
        raise ValueError('conditioning torque fit did not resolve')
    slope, offset, _ = fit.x
    fitted = slope*x+offset
    residual = np.abs(fitted-q)
    relative = float(np.max(np.divide(residual, q, out=np.zeros_like(q), where=q > 0)))
    if np.any((q == 0) & (residual > 1e-10)) or relative > policy.torque_relative_residual_tolerance+1e-10:
        raise ValueError(f'torque relative residual {relative:.8g} exceeds declared conditioning tolerance')
    band = float(np.max(residual+q*policy.torque_relative_uncertainty/(1-policy.torque_relative_uncertainty)))
    efficiency = model.efficiency if model.power_basis == 'shaft' else 1.
    electrical = np.array([p.power_w for p in model.points])/efficiency
    sample_upper = electrical/(1-policy.power_relative_uncertainty)
    # Also bound the fitted upper torque's shaft demand. Between sample points,
    # torque and RPM are increasing affine functions of thrust: their product is
    # convex, so endpoint secants bound it above throughout each interval.
    target = np.maximum(sample_upper, (fitted+band)*rpm*2*np.pi/60/efficiency)
    power, shift = upper_envelope(x, target)
    if shift > policy.max_power_shift_fraction*max(float(np.max(target)), 1e-12)+1e-10:
        raise ValueError('power hull shift exceeds declared conditioning tolerance')
    slopes = np.diff(power)/np.diff(x)
    if np.any(slopes < -1e-10) or np.any(np.diff(slopes) < -1e-8) or np.any(power+1e-9 < target):
        raise ValueError('conditioned power cannot establish a nondecreasing conservative convex envelope')
    return {'schema_version': 'conditioned_rotor_profile_v1', 'policy': policy.model_dump(mode='json'),
            'thrust_n': x.tolist(), 'rpm': rpm.tolist(), 'electrical_power_w': power.tolist(),
            'sample_upper_electrical_power_w': target.tolist(), 'power_shift_w': shift,
            'torque_slope_nm_per_n': float(slope), 'torque_offset_nm': float(offset),
            'torque_max_relative_residual': relative, 'torque_error_bound_nm': band,
            'qualification': 'Conservative relative to the declared sample/uncertainty envelope. '
                             'No between-sample measurement or installed-aircraft validation.'}


@dataclass(frozen=True)
class ConditionedMap:
    raw: RotorMapV1
    source_sha256: str
    conditioned_sha256: str
    profile: dict

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def convex_static_profile(self):
        p = self.profile
        x = np.array(p['thrust_n']); power = np.array(p['electrical_power_w'])
        slopes = np.diff(power)/np.diff(x)
        return {'thrust': x, 'rpm': np.array(p['rpm']), 'power': power,
                'power_slopes': slopes, 'power_offsets': power[:-1]-slopes*x[:-1],
                'torque_slope': p['torque_slope_nm_per_n'], 'torque_offset': p['torque_offset_nm'],
                'torque_error_bound_nm': p['torque_error_bound_nm']}

    def evaluate(self, rpm, *, density, inflow, pitch):
        self.raw.check_query(rpm, density=density, inflow=inflow, pitch=pitch)
        thrust = float(np.interp(rpm, self.profile['rpm'], self.profile['thrust_n']))
        return {'rpm': rpm, 'thrust_n': thrust,
                'shaft_torque_nm': self.profile['torque_slope_nm_per_n']*thrust+self.profile['torque_offset_nm'],
                'electrical_power_w': float(np.interp(thrust, self.profile['thrust_n'],
                                                     self.profile['electrical_power_w'])),
                'scope': 'Conditioned fixed-condition curve; declared torque band; physical validation pending.'}

    def evidence(self):
        return {'raw_source_sha256': self.source_sha256, 'conditioned_source_sha256': self.conditioned_sha256,
                'profile_sha256': sha256_record(self.profile), **self.profile}
