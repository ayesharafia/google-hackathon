"""Source-bound, fixed-configuration rotor curves with explicit coverage."""
from __future__ import annotations

import math
from itertools import pairwise
from typing import Annotated, Literal

import numpy as np
from pydantic import Field, model_validator

from physimesh.projects.contracts import Identifier, Record

Positive = Annotated[float, Field(gt=0)]
Nonnegative = Annotated[float, Field(ge=0)]


class MapPoint(Record):
    rpm: Nonnegative
    thrust_n: Nonnegative
    shaft_torque_nm: Nonnegative
    power_w: Nonnegative


class RotorMapV1(Record):
    schema_version: Literal['rotor_map_v1'] = 'rotor_map_v1'
    dataset_id: Identifier
    configuration_id: Identifier
    source_kind: Literal['analytic_fixture', 'measured']
    source_description: str = Field(min_length=1, max_length=2000)
    units: Literal['rpm_N_Nm_W']
    torque_convention: Literal['absorbed_shaft_magnitude']
    density_kg_m3: Positive
    axial_inflow_m_s: float
    pitch_deg: float
    max_continuous_duration_s: Positive
    power_basis: Literal['electrical', 'shaft']
    efficiency: Annotated[float, Field(gt=0, le=1)] | None = None
    efficiency_source: str | None = None
    covered_intervals_rpm: tuple[tuple[Nonnegative, Nonnegative], ...] = Field(min_length=1, max_length=32)
    points: tuple[MapPoint, ...] = Field(min_length=2, max_length=64)

    @model_validator(mode='after')
    def consistency(self):
        rpms = [point.rpm for point in self.points]
        if any(b <= a for a, b in pairwise(rpms)):
            raise ValueError('map RPM points must be strictly increasing without duplicates')
        if self.power_basis == 'shaft' and (self.efficiency is None or not self.efficiency_source
                                           or not self.efficiency_source.strip()):
            raise ValueError('shaft power requires a declared efficiency and its source')
        if self.power_basis == 'electrical' and (self.efficiency is not None or self.efficiency_source is not None):
            raise ValueError('measured electrical watts cannot apply efficiency again')
        for point in self.points:
            absorbed = point.shaft_torque_nm * point.rpm * 2 * math.pi / 60
            if point.power_w + 1e-9 * max(1, absorbed) < absorbed:
                raise ValueError('power is smaller than torque times angular speed')
            if self.power_basis == 'shaft' and not math.isclose(point.power_w, absorbed, rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError('shaft watts must agree with absorbed torque times angular speed')
        for low, high in self.covered_intervals_rpm:
            if not rpms[0] <= low < high <= rpms[-1]:
                raise ValueError('covered intervals must be inside the retained RPM range')
            if low not in rpms or high not in rpms:
                raise ValueError('each covered interval boundary must be a retained sample; interpolation cannot bridge holes')
        ordered = sorted(self.covered_intervals_rpm)
        if any(b[0] < a[1] for a, b in pairwise(ordered)):
            raise ValueError('covered intervals overlap')
        if not self.source_description.strip():
            raise ValueError('source description cannot be blank')
        return self

    def evaluate(self, rpm: float, *, density: float, inflow: float, pitch: float) -> dict:
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in (rpm, density, inflow, pitch)):
            raise ValueError('query values must be finite numbers')
        if not math.isclose(density, self.density_kg_m3, rel_tol=1e-9, abs_tol=0):
            raise ValueError('density outside fixed-density map coverage')
        if not math.isclose(inflow, self.axial_inflow_m_s, abs_tol=1e-9, rel_tol=0):
            raise ValueError('inflow outside map coverage')
        if not math.isclose(pitch, self.pitch_deg, abs_tol=1e-9, rel_tol=0):
            raise ValueError('pitch outside map coverage')
        if not any(low <= rpm <= high for low, high in self.covered_intervals_rpm):
            raise ValueError('RPM query outside explicitly covered intervals')
        x = [point.rpm for point in self.points]
        power = float(np.interp(rpm, x, [point.power_w for point in self.points]))
        torque = float(np.interp(rpm, x, [p.shaft_torque_nm for p in self.points]))
        shaft = torque*rpm*2*math.pi/60
        if self.power_basis == 'shaft':
            power = shaft
        elif power+1e-9*max(1., shaft) < shaft:
            raise ValueError('interpolated electrical watts below absorbed shaft demand')
        return {'rpm': rpm, 'thrust_n': float(np.interp(rpm, x, [p.thrust_n for p in self.points])),
                'shaft_torque_nm': torque,
                'electrical_power_w': power if self.power_basis == 'electrical' else power / self.efficiency,
                'scope': 'Isolated fixed-condition curve; installed-aircraft validation pending.'}

    def convex_static_profile(self) -> dict:
        """Exact restricted piecewise-linear model, not a fit to arbitrary nonlinear maps."""
        x = np.array([point.thrust_n for point in self.points])
        torque = np.array([point.shaft_torque_nm for point in self.points])
        power = np.array([point.power_w for point in self.points])
        if self.power_basis == 'shaft':
            if not np.allclose(torque, torque[0], rtol=1e-10, atol=1e-10):
                raise ValueError('initial linear trim supports shaft curves only with constant absorbed torque')
            power = power / self.efficiency
        if (len(self.covered_intervals_rpm) != 1 or self.covered_intervals_rpm[0]
                != (self.points[0].rpm, self.points[-1].rpm)):
            raise ValueError('trim profile requires one explicitly covered full RPM interval')
        if np.any(np.diff(x) <= 0):
            raise ValueError('trim profile requires strictly increasing thrust')
        slopes = np.diff(power) / np.diff(x)
        if np.any(slopes < 0) or np.any(np.diff(slopes) < -1e-10):
            raise ValueError('trim profile requires nondecreasing convex electrical power versus thrust')
        q_slope = float((torque[-1] - torque[0]) / (x[-1] - x[0]))
        q_offset = float(torque[0] - q_slope * x[0])
        if not np.allclose(torque, q_slope * x + q_offset, rtol=1e-10, atol=1e-10):
            raise ValueError('trim profile requires affine absorbed torque versus thrust')
        if q_slope < 0:
            raise ValueError('trim profile requires nondecreasing absorbed torque')
        return {'thrust': x, 'power': power, 'power_slopes': slopes,
                'power_offsets': power[:-1] - slopes * x[:-1],
                'torque_slope': q_slope, 'torque_offset': q_offset,
                'rpm': np.array([point.rpm for point in self.points])}
