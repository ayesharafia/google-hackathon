"""Versioned application input contract and conservative readiness [M§26].

Readiness checks inputs, never CFD capability or engineering validation [M§2].
The reconstructed template awaits comparison with the client's companion YAML (Q10).
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

import numpy as np
import yaml

from .atmosphere import make_atmosphere
from .geometry import ROLES
from .mass import MassItem, summarize
from .units import DIM_KINEMATIC_PRESSURE, DIM_PRESSURE_PA, length_factor, parse_foam_dimensions


class AircraftStatus(str, Enum):
    INPUTS_INCOMPLETE = "inputs_incomplete"
    SCREENING_ONLY = "screening_only"
    NUMERICALLY_UNVERIFIED = "numerically_unverified"
    VALIDATION_PENDING = "validation_pending"
    WITHIN_VALIDATED_ENVELOPE = "within_validated_envelope"
    REQUIREMENT_NOT_MET = "requirement_not_met"


class ExecutionState(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    MESHING = "meshing"
    RUNNING = "running"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class EvidenceLevel(str, Enum):
    UNVERIFIED = "unverified"
    ITERATION_CONVERGED = "iteration_converged"
    PERIODIC_OR_STATISTICAL_CONVERGED = "periodic_or_statistical_converged"
    MESH_ASSESSED = "mesh_assessed"
    TIME_ASSESSED = "time_assessed"
    VALIDATED_FOR_CASE_FAMILY = "validated_for_case_family"


class Fidelity(str, Enum):
    MEASURED_MAP = "measured_map"
    BEM = "bem"
    ACTUATOR_DISK = "actuator_disk"
    ACTUATOR_LINE = "actuator_line"
    STEADY_ROTATING_FRAME = "steady_rotating_frame"
    TRANSIENT_MESH = "transient_mesh"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class ProjectSnapshot:
    """Deeply immutable parsed groups; all dimensions follow the named SI fields."""
    identity: Mapping
    units_and_frames: Mapping
    mission: Mapping
    masses: Mapping
    atmosphere: Mapping
    assembly: Mapping
    rotors: tuple
    flow: Mapping
    fidelity: Mapping
    symmetry: Mapping
    domain: Mapping
    mesh: Mapping
    numerics: Mapping
    boundaries: Mapping
    convergence: Mapping
    postprocessing: Mapping
    validation: Mapping
    execution: Mapping

    def __post_init__(self) -> None:
        for field in fields(self):
            object.__setattr__(self, field.name, _freeze(getattr(self, field.name)))


def load_project(path: str | Path) -> ProjectSnapshot:
    """Load safe YAML without replacing nulls; reject unknown versions/groups [M§26]."""
    return project_from_mapping(yaml.safe_load(Path(path).read_text()))


def project_from_mapping(data: Any) -> ProjectSnapshot:
    """Validate an already-parsed project (YAML or JSON body) with the same rules as load_project."""
    if not isinstance(data, dict):
        raise TypeError("project must be a mapping")
    groups = {f.name for f in fields(ProjectSnapshot)}
    if set(data) != groups:
        raise ValueError(f"project groups: missing {sorted(groups - set(data))}; extra {sorted(set(data) - groups)}")
    for name, value in data.items():
        if name == "rotors":
            if not isinstance(value, list) or any(not isinstance(r, dict) for r in value):
                raise ValueError("rotors must be a list of mappings")
        elif not isinstance(value, dict):
            raise ValueError(f"{name} must be a mapping")
    if data["identity"].get("schema_version") != "drone_manifest_v1":
        raise ValueError("unsupported identity.schema_version")
    return ProjectSnapshot(**data)


ROTOR_MODELS = ("measured_map", "bem", "actuator_disk", "actuator_line", "blade_resolved")  # [plan Appendix A]


@dataclass(frozen=True)
class ReadinessReport:
    """Blocking input paths and warnings.

    ready=True means only that the inputs for `purpose` are present and well-formed.
    Readiness never assigns a higher aircraft status: with no blocking items, status
    is None until screening or CFD actually runs (plan §4.1, §0 rule 6).
    """
    purpose: str
    blocking: list[str]
    warnings: list[str]
    status: AircraftStatus | None
    ready: bool


def readiness(snapshot: ProjectSnapshot,
              purpose: Literal["screening", "cfd_run", "feasibility"]) -> ReadinessReport:
    """Check declared SI inputs [plan Task 2.5]; no inferred units, rotor data or capability."""
    if purpose not in ("screening", "cfd_run", "feasibility"):
        raise ValueError(f"unknown readiness purpose {purpose!r}")
    blocking: list[str] = []
    warnings: list[str] = []

    def present(value: Any) -> bool:
        if isinstance(value, str):
            return bool(value.strip())
        return value is not None and value != () and value != {}

    def vector3(value: Any, path: str, *, nonzero: bool = False) -> None:
        try:
            v = np.asarray(value, float)
            ok = v.shape == (3,) and bool(np.isfinite(v).all()) and (not nonzero or bool(np.any(v)))
        except (TypeError, ValueError):
            ok = False
        if not ok:
            blocking.append(path)

    def require(value: Any, path: str) -> bool:
        """Present and, for mappings/sequences, every nested value present."""
        is_present = present(value)
        if not is_present:
            blocking.append(path)
        elif isinstance(value, Mapping):
            for key, child in value.items():
                require(child, f"{path}.{key}")
        elif isinstance(value, tuple):
            for i, child in enumerate(value):
                require(child, f"{path}[{i}]")
        elif isinstance(value, (int, float)) and not math.isfinite(value):
            blocking.append(path)
        return is_present

    def positive(value: Any, path: str) -> bool:
        valid = isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and value > 0
        if not valid:
            blocking.append(path)
        return valid

    template = yaml.safe_load(Path(__file__).with_name("schema").joinpath("drone_manifest_v1.yaml").read_text())

    # Record keys from Appendix A; preserve unrecognised client extensions [M§26].
    template["assembly"]["components"] = [{k: None for k in
        ("component_id", "role", "rotor_id", "requires_user_tag")} ]
    template["atmosphere"]["viscosity"] = {"law": None, "value_pa_s": None}

    def unknown(actual: Mapping, expected: Mapping, prefix: str) -> None:
        for key, value in actual.items():
            path = f"{prefix}.{key}"
            if key not in expected:
                warnings.append(f"unknown key retained: {path}")
            elif isinstance(value, Mapping) and isinstance(expected[key], dict):
                unknown(value, expected[key], path)
            elif isinstance(value, tuple) and isinstance(expected[key], list) and expected[key]:
                shape = expected[key][0]
                if isinstance(shape, dict):
                    for i, record in enumerate(value):
                        if isinstance(record, Mapping):
                            unknown(record, shape, f"{path}[{i}]")

    for field in fields(snapshot):
        value = getattr(snapshot, field.name)
        if isinstance(value, Mapping):
            unknown(value, template[field.name], field.name)

    payload = snapshot.mission.get("payload_mass_kg")
    # Optional installed payload for this case; no fixed target [USER 2026-10-02].
    if payload is not None and (isinstance(payload, bool) or not isinstance(payload, (int, float))
                                or not math.isfinite(payload) or payload < 0):
        blocking.append("mission.payload_mass_kg (must be finite kg >= 0 when supplied)")
    try:
        items = snapshot.masses.get("items")
        if not isinstance(items, tuple):
            raise TypeError("items must be a list")
        known = {f.name for f in fields(MassItem)}
        ledger = []
        for i, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise TypeError("mass item must be a mapping")
            for key in item.keys() - known:
                warnings.append(f"unknown key retained: masses.items[{i}].{key}")
            ledger.append(MassItem(**{k: v for k, v in item.items() if k in known}))
        result = summarize(ledger)
        blocking.extend(result.missing + result.errors)
        if (payload is not None and isinstance(payload, (int, float)) and not isinstance(payload, bool)
                and math.isfinite(payload) and result.complete
                and not math.isclose(payload, result.payload_kg, rel_tol=0, abs_tol=1e-9)):
            # 1e-9 kg is representation tolerance, not an engineering acceptance gate [ASSUMPTION].
            blocking.append("mission.payload_mass_kg (must match the payload mass ledger)")
    except (ValueError, TypeError, OverflowError) as exc:
        blocking.append(f"masses.items ({exc})")

    atm = snapshot.atmosphere
    for key in ("pressure_pa", "temperature_k"):
        positive(atm.get(key), f"atmosphere.{key}")
    require(atm.get("source"), "atmosphere.source")
    viscosity = atm.get("viscosity")
    try:
        if not isinstance(viscosity, Mapping):
            raise TypeError("declare value_pa_s or approved law")
        make_atmosphere(atm.get("pressure_pa"), atm.get("temperature_k"),
                        source=atm.get("source"), gamma=atm.get("gamma"),
                        viscosity_pa_s=viscosity.get("value_pa_s"), viscosity_law=viscosity.get("law"))
    except (ValueError, TypeError, OverflowError) as exc:
        blocking.append(f"atmosphere.viscosity ({exc})")

    if not snapshot.rotors:
        blocking.append("rotors (count must be declared)")
    rotor_keys = {"rotor_id", "center_body_m", "axis_body", "signed_rpm", "pitch_deg", "n_blades",
                  "radius_m", "root_cutout_m", "azimuth_zero_deg", "phase_offset_deg", "model", "map_ref",
                  "blade_ref", "polar_ref", "sustained_limits", "peak_limits"}  # [plan Appendix A]
    # Record-shaped nulls are allowed: each purpose requires only the fields it uses.
    for i, rotor in enumerate(snapshot.rotors):
        prefix = f"rotors[{i}]"
        for key in rotor.keys() - rotor_keys:
            warnings.append(f"unknown key retained: {prefix}.{key}")
        require(rotor.get("rotor_id"), f"{prefix}.rotor_id")
        positive(rotor.get("radius_m"), f"{prefix}.radius_m")
        model = rotor.get("model")
        if model is not None and model not in ROTOR_MODELS:
            blocking.append(f"{prefix}.model")
        if not present(rotor.get("map_ref")) and not (present(rotor.get("blade_ref"))
                                                      and present(rotor.get("polar_ref"))):
            blocking.append(f"{prefix}.map_ref or blade_ref + polar_ref")
        if purpose in ("cfd_run", "feasibility"):
            # A rotor frame is mandatory to build a rotating zone or source [M§3].
            vector3(rotor.get("center_body_m"), f"{prefix}.center_body_m")
            vector3(rotor.get("axis_body"), f"{prefix}.axis_body", nonzero=True)
            rpm = rotor.get("signed_rpm")
            if isinstance(rpm, bool) or not isinstance(rpm, (int, float)) or not math.isfinite(rpm):
                blocking.append(f"{prefix}.signed_rpm")
            if model == "blade_resolved" and (rotor.get("azimuth_zero_deg") is None
                                              or rotor.get("phase_offset_deg") is None):
                # Mandatory only for blade-resolved transient comparisons [M§3]; enforced at
                # transient case generation by RotorFrame.require_phase().
                warnings.append(f"{prefix}: azimuth_zero_deg/phase_offset_deg required before any "
                                "transient blade-resolved run")
        if purpose == "feasibility":
            for key in ("sustained_limits", "peak_limits"):
                require(rotor.get(key), f"{prefix}.{key}")

    if purpose in ("cfd_run", "feasibility"):
        try:
            length_factor(snapshot.units_and_frames.get("source_units"))
        except ValueError:
            blocking.append("units_and_frames.source_units")
        geometry_hash = snapshot.assembly.get("geometry_revision_sha256")
        if not isinstance(geometry_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", geometry_hash):
            blocking.append("assembly.geometry_revision_sha256")
        components = snapshot.assembly.get("components")
        rotor_ids = {r.get("rotor_id") for r in snapshot.rotors}
        if not components:
            blocking.append("assembly.components")
        else:
            # Static parts legitimately have rotor_id null; no blanket recursion [M§11].
            for i, component in enumerate(components):
                prefix = f"assembly.components[{i}]"
                if not isinstance(component, Mapping):
                    blocking.append(prefix)
                    continue
                require(component.get("component_id"), f"{prefix}.component_id")
                role = component.get("role")
                if role not in ROLES:
                    blocking.append(f"{prefix}.role")
                if role in ("blade", "hub") and component.get("rotor_id") not in rotor_ids:
                    blocking.append(f"{prefix}.rotor_id")
                if component.get("requires_user_tag") is True:
                    blocking.append(f"{prefix}.requires_user_tag")
        zones = snapshot.mesh.get("rotation_zones")
        for i, rotor in enumerate(snapshot.rotors):
            if not isinstance(zones, Mapping):
                blocking.append(f"mesh.rotation_zones[{i}]")
            else:
                require(zones.get(rotor.get("rotor_id")), f"mesh.rotation_zones[{i}]")
        positive(snapshot.mesh.get("global_cell_m"), "mesh.global_cell_m")
        positive(snapshot.mesh.get("max_cells"), "mesh.max_cells")
        try:
            bounds = np.asarray(snapshot.domain.get("bounds_m"), float)
            if bounds.shape != (2, 3) or not np.isfinite(bounds).all() or not (bounds[1] > bounds[0]).all():
                raise ValueError("finite lower/upper 3-vectors with positive extents required")
        except (ValueError, TypeError):
            blocking.append("domain.bounds_m")
        for key in ("backend_version", "backend_image_digest"):
            require(snapshot.execution.get(key), f"execution.{key}")
        digest = snapshot.execution.get("backend_image_digest")
        if digest and (not isinstance(digest, str) or not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", digest)):
            blocking.append("execution.backend_image_digest (immutable image reference required)")
        for key in ("far_field", "outlet", "ground_model", "walls"):
            require(snapshot.boundaries.get(key), f"boundaries.{key}")
        # Application declaration added to the reconstructed contract [ASSUMPTION: field name].
        dims = snapshot.flow.get("pressure_dimensions")
        try:
            parsed = parse_foam_dimensions(dims) if isinstance(dims, str) else tuple(dims)
            if parsed not in (DIM_PRESSURE_PA, DIM_KINEMATIC_PRESSURE):
                raise ValueError("unsupported pressure dimensions")
        except (ValueError, TypeError):
            blocking.append("flow.pressure_dimensions")
        if snapshot.symmetry.get("execution") != "off":
            blocking.append("symmetry.execution (eligibility and full-domain comparison pending)")

    if purpose == "feasibility":
        positive(snapshot.mission.get("duration_s"), "mission.duration_s")
        require(snapshot.mission.get("reserve_policy"), "mission.reserve_policy")
        # Energy specification complements mass only [ASSUMPTION: field name; plan Task 2.5].
        require(snapshot.mission.get("energy_system"), "mission.energy_system")
    status = AircraftStatus.INPUTS_INCOMPLETE if blocking else None
    warnings.append("Input readiness does not establish backend capability or engineering validation.")
    return ReadinessReport(purpose, list(dict.fromkeys(blocking)), warnings, status, not blocking)
