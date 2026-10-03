"""Conservative payload-capacity screening from declared operating limits.

This module combines *resolved* rotor and body force inputs. It does not infer
thrust from STL geometry, solve trim or validate a rotor model [M§5; USER 2026-10-02].
Callers must resolve the source hashes to retained artifacts before publication.
"""
from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real

import numpy as np

from .atmosphere import G0
from .mass import MassSummary
from .models import AircraftStatus

_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class RotorLimitPoint:
    """Rotor force on aircraft (world N) and electric W at an approved sustained limit."""

    rotor_id: str
    force_world_n: tuple[float, float, float]
    electrical_power_w: float
    sustained_electrical_power_limit_w: float
    performance_source_sha256: str
    limit_source_sha256: str


@dataclass(frozen=True)
class CapacityCaseInput:
    """One required mission condition, including body force and energy limits.

    Rotor points must already account for altitude, attitude, motor and reserve
    policy. Body force is positive upward. No missing body download is set to 0.
    """

    case_id: str
    rotors: tuple[RotorLimitPoint, ...]
    body_force_world_n: tuple[float, float, float]
    body_force_source_sha256: str
    vertical_acceleration_m_s2: float
    duration_s: float
    available_electrical_power_w: float


@dataclass(frozen=True)
class CaseCapacity:
    """Vertical-force-limited payload result in kg for one declared case."""

    case_id: str
    vertical_force_n: float
    supported_total_mass_kg: float
    raw_payload_margin_kg: float
    max_payload_kg: float
    electrical_power_w: float
    energy_required_j: float
    source_sha256: tuple[str, ...]


@dataclass(frozen=True)
class CapacityReport:
    """Minimum of all complete required cases; never a validation certificate."""

    max_payload_kg: float | None
    limiting_case_id: str | None
    cases: tuple[CaseCapacity, ...]
    empty_airframe_mass_kg: float | None
    status: AircraftStatus
    blocking: tuple[str, ...]
    interpretation: str
    outcome: str = "vertical_screening_ceiling"
    reasons: tuple[dict, ...] = ()
    trim_eligibility: str = "not_evaluated"


def _finite_nonnegative(value: object) -> bool:
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _vector3(value: object) -> np.ndarray | None:
    try:
        raw = np.asarray(value, object)
        if raw.shape != (3,) or any(isinstance(v, bool) or not isinstance(v, Real) for v in raw):
            return None
        array = np.asarray(value, float)
    except (TypeError, ValueError, OverflowError):
        return None
    if array.shape != (3,) or not bool(np.isfinite(array).all()):
        return None
    return array


def capacity_from_cases(mass: MassSummary, declared_case_ids: Sequence[str],
                        case_inputs: Sequence[CapacityCaseInput], *,
                        usable_energy_j: float) -> CapacityReport:
    """Compute kg of payload supportable in every required mission case.

    Implements: [M-E05] in world z, m_supported = (ΣF_rotor,z + F_body,z) /
    (g₀ + a_z); payload margin is supported total mass minus empty airframe
    mass [M-E01, USER 2026-10-02]. Rotor forces are N; acceleration is m/s²;
    duration is s, electric power W, usable battery energy J. Energy is checked
    independently for each *alternative* operating case (E46); case energies
    are not summed as if the cases were sequential mission segments. A limiting
    operating point without enough power or energy cannot yield a capacity.

    This is a vertical-force screening ceiling. It excludes trim/control,
    structural margins, varying body load and model/measurement uncertainty.
    """
    blocking: list[str] = []
    infeasible: list[dict] = []
    unsupported: list[dict] = []
    empty_mass = mass.empty_airframe_mass_kg
    if empty_mass is None or not math.isfinite(empty_mass) or empty_mass < 0:
        blocking.append("masses: complete finite empty-airframe ledger required")
    if not _finite_nonnegative(usable_energy_j) or usable_energy_j == 0:
        blocking.append("mission.usable_energy_j: finite positive value required")
    ids = tuple(declared_case_ids)
    if not ids or any(not isinstance(identifier, str) or not identifier.strip() for identifier in ids):
        blocking.append("mission.cases: at least one named case required")
    if len(set(ids)) != len(ids):
        blocking.append("mission.cases: duplicate case_id")
    supplied = tuple(case_inputs)
    supplied_ids = [case.case_id for case in supplied]
    if len(set(supplied_ids)) != len(supplied_ids):
        blocking.append("capacity inputs: duplicate case_id")
    for identifier in ids:
        if identifier not in supplied_ids:
            blocking.append(f"mission.cases[{identifier}]: capacity inputs missing")
    for identifier in supplied_ids:
        if identifier not in ids:
            blocking.append(f"capacity inputs[{identifier}]: case not declared")

    calculated: list[CaseCapacity] = []
    by_id = {case.case_id: case for case in supplied}
    for identifier in ids:
        case = by_id.get(identifier)
        if case is None:
            continue
        path = f"mission.cases[{identifier}]"
        body_force = _vector3(case.body_force_world_n)
        if body_force is None:
            blocking.append(f"{path}.body_force_world_n")
        if not isinstance(case.body_force_source_sha256, str) or not _SHA256.fullmatch(case.body_force_source_sha256):
            blocking.append(f"{path}.body_force_source_sha256")
        if isinstance(case.vertical_acceleration_m_s2, bool) or not isinstance(case.vertical_acceleration_m_s2, (int, float)) or not math.isfinite(
            case.vertical_acceleration_m_s2
        ) or G0 + case.vertical_acceleration_m_s2 <= 0:
            blocking.append(f"{path}.vertical_acceleration_m_s2")
        if not _finite_nonnegative(case.duration_s) or case.duration_s == 0:
            blocking.append(f"{path}.duration_s")
        if not _finite_nonnegative(case.available_electrical_power_w) or case.available_electrical_power_w == 0:
            blocking.append(f"{path}.available_electrical_power_w")
        if not case.rotors:
            blocking.append(f"{path}.rotors")
        rotor_ids = [rotor.rotor_id for rotor in case.rotors]
        if len(set(rotor_ids)) != len(rotor_ids):
            blocking.append(f"{path}.rotors: duplicate rotor_id")
        forces: list[np.ndarray] = []
        powers: list[float] = []
        sources = [case.body_force_source_sha256]
        for rotor in case.rotors:
            rotor_path = f"{path}.rotors[{rotor.rotor_id}]"
            force = _vector3(rotor.force_world_n)
            if force is None:
                blocking.append(f"{rotor_path}.force_world_n")
            else:
                forces.append(force)
            if not _finite_nonnegative(rotor.electrical_power_w):
                blocking.append(f"{rotor_path}.electrical_power_w")
            elif not _finite_nonnegative(rotor.sustained_electrical_power_limit_w):
                blocking.append(f"{rotor_path}.sustained_electrical_power_limit_w")
            elif rotor.electrical_power_w > rotor.sustained_electrical_power_limit_w:
                infeasible.append({"category": "infeasible_limits", "code": "motor_power_exceeded",
                                   "detail": f"{rotor_path}: sustained motor power exceeded",
                                   "actual_w": rotor.electrical_power_w, "limit_w": rotor.sustained_electrical_power_limit_w})
                powers.append(rotor.electrical_power_w)
            else:
                powers.append(rotor.electrical_power_w)
            for field_name in ("performance_source_sha256", "limit_source_sha256"):
                digest = getattr(rotor, field_name)
                if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                    blocking.append(f"{rotor_path}.{field_name}")
                else:
                    sources.append(digest)
        if any(item.startswith(path) for item in blocking) or empty_mass is None:
            continue
        if blocking:
            continue
        try:
            power = math.fsum(powers)
        except OverflowError:
            blocking.append(f"{path}: electrical power overflowed")
            continue
        if not math.isfinite(power):
            blocking.append(f"{path}: electrical power overflowed")
            continue
        if power > case.available_electrical_power_w:
            infeasible.append({"category": "infeasible_limits", "code": "available_power_exceeded",
                               "detail": f"{path}: available electrical power exceeded",
                               "actual_w": power, "limit_w": case.available_electrical_power_w})
        energy = power * case.duration_s
        if not math.isfinite(energy):
            blocking.append(f"{path}: energy overflowed")
            continue
        if energy > usable_energy_j:
            infeasible.append({"category": "infeasible_limits", "code": "usable_energy_exceeded",
                               "detail": f"{path}: usable energy insufficient at the stated operating point",
                               "actual_j": energy, "limit_j": usable_energy_j})
        try:
            horizontal = [math.fsum(float(f[axis]) for f in [*forces, body_force]) for axis in (0, 1)]
            scale_n = max(1.0, math.fsum(math.hypot(*f) for f in [*forces, body_force]))
        except OverflowError:
            blocking.append(f'{path}: horizontal force/scale overflowed')
            continue
        if not all(map(math.isfinite, [*horizontal, scale_n])):
            blocking.append(f'{path}: horizontal force/scale nonfinite')
            continue
        if math.hypot(*horizontal) > 1e-9 * scale_n:
            unsupported.append({"category": "unsupported_scope", "code": "horizontal_balance_unresolved",
                                "detail": f"{path}: horizontal force balance requires trim",
                                "residual_n": horizontal, "numerical_tolerance_n": 1e-9 * scale_n})
        try:
            net_z = math.fsum([*(float(force[2]) for force in forces), float(body_force[2])])
        except OverflowError:
            blocking.append(f"{path}: force overflowed")
            continue
        supported = net_z / (G0 + case.vertical_acceleration_m_s2)
        raw_margin = supported - empty_mass
        if not all(map(math.isfinite, (net_z, supported, raw_margin))):
            blocking.append(f"{path}: force or capacity overflowed")
            continue
        calculated.append(CaseCapacity(identifier, net_z, supported, raw_margin,
                                       max(0., raw_margin), power, energy, tuple(sources)))

    if blocking:
        return CapacityReport(None, None, tuple(calculated), empty_mass,
                              AircraftStatus.INPUTS_INCOMPLETE, tuple(dict.fromkeys(blocking)),
                              "Capacity unavailable until every declared case and operating limit is complete.",
                              "inputs_incomplete", tuple([{"category": "inputs_incomplete", "code": "missing_or_invalid_input",
                                                           "detail": item} for item in dict.fromkeys(blocking)] + infeasible + unsupported))
    if infeasible or unsupported:
        reasons = tuple(infeasible + unsupported)
        outcome = "infeasible_limits" if infeasible else "unsupported_scope"
        status = AircraftStatus.REQUIREMENT_NOT_MET if infeasible else AircraftStatus.INPUTS_INCOMPLETE
        return CapacityReport(None, None, tuple(calculated), empty_mass, status,
                              tuple(reason["detail"] for reason in reasons),
                              "No capacity is published for infeasible limits or unresolved trim.", outcome, reasons)
    limiting = min(calculated, key=lambda item: item.raw_payload_margin_kg)
    status = (AircraftStatus.REQUIREMENT_NOT_MET if limiting.raw_payload_margin_kg < 0
              else AircraftStatus.SCREENING_ONLY)
    return CapacityReport(limiting.max_payload_kg, limiting.case_id, tuple(calculated),
                          empty_mass, status, (),
                          "Vertical-force screening ceiling at supplied limits; trim and validation remain pending.")
