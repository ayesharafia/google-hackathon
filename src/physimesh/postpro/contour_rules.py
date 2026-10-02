"""Deterministic evidence selection [M§22], [M§23], [M§33] and range policy [M§24].

The engine picks evidence from the engineering question + capability + provenance.
It never picks a plot for visual appeal and never invents a missing field.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

INTENTS = ("payload_lift", "rotor_thrust", "rotor_power", "body_download", "interference",
           "separation", "compressibility", "ground_effect", "numerical_quality",
           "symmetry_comparison")


@dataclass(frozen=True)
class CapabilityManifest:
    """Step 2 [M§22]: what the case actually contains."""
    has_blade_walls: bool
    has_actuator_sources: bool
    pressure_kind: str | None          # "pa" | "kinematic" | None (unknown)
    has_wall_stress: bool
    velocity_frame: str | None         # "absolute" | "relative" | None
    density_known: bool
    has_volume_fields: bool
    has_gradients: bool
    has_relative_velocity: bool
    has_yplus: bool
    turbulent_walls: bool
    accepted_time_window: bool
    reference_speed_m_s: float | None = None
    has_force_history: bool = True


@dataclass(frozen=True)
class PlotSpec:
    field_id: str
    role: str                # "mandatory" | "explanatory"
    note: str = ""


@dataclass(frozen=True)
class Missing:
    item: str
    next_action: str


@dataclass
class EvidencePlan:
    intent: str
    selected: list[PlotSpec] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    missing: list[Missing] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing


def select_evidence(intent: str, cap: CapabilityManifest, *, requested: Sequence[str] = (),
                    time_mode: str = "mean") -> EvidencePlan:
    """Steps 3-4 [M§22]. `requested` lists user-asked fields; prerequisites still apply."""
    if intent not in INTENTS:
        raise ValueError(f"unsupported intent {intent!r}")
    plan = EvidencePlan(intent)
    sel, miss, rej = plan.selected, plan.missing, plan.rejected

    def need(cond: bool, item: str, action: str) -> bool:
        if not cond:
            miss.append(Missing(item, action))
        return cond

    pressure_ok = cap.pressure_kind == "pa" or (cap.pressure_kind == "kinematic" and cap.density_known)

    if time_mode == "mean" and not cap.accepted_time_window:
        rej.append("averaged fields: no accepted averaging window")
        miss.append(Missing("accepted averaging window",
                            "extend run / accept statistics window before mean plots"))

    if intent == "payload_lift":
        if cap.has_blade_walls:
            if need(pressure_ok, "pressure semantics", "declare density / pressure dimensions"):
                sel.append(PlotSpec("traction.world_z", "mandatory"))
        elif cap.has_actuator_sources:
            sel.append(PlotSpec("source.rotor_reaction", "mandatory",
                                "prescribed loads must be labelled as inputs"))
            sel.append(PlotSpec("traction.world_z", "mandatory", "body surfaces only"))
            rej.append("blade pressure: source-only rotor has no blade surface")
        else:
            need(False, "rotor load representation", "add blade walls or actuator sources")
        need(cap.has_force_history, "load.thrust_history", "enable force function objects")
        sel.append(PlotSpec("load.thrust_history", "mandatory"))
        sel.append(PlotSpec("balance.E05", "mandatory", "force ledger vs weight"))
        rej.append("pressure magnitude alone as lift evidence")
    elif intent == "rotor_power":
        if need(cap.has_blade_walls and cap.has_wall_stress, "blade walls with wall stress",
                "export wall shear stress / run blade-resolved model"):
            sel.append(PlotSpec("moment_density.rotor_axial", "explanatory"))
        sel.append(PlotSpec("load.torque_history", "mandatory"))
        sel.append(PlotSpec("load.shaft_power_signed", "mandatory"))
        rej.append("speed contour as power evidence")
    elif intent == "rotor_thrust":
        if cap.has_blade_walls and pressure_ok:
            sel.append(PlotSpec("traction.rotor_axial", "explanatory"))
        elif cap.has_actuator_sources:
            sel.append(PlotSpec("source.rotor_reaction", "mandatory"))
            rej.append("blade pressure: source-only rotor")
        sel.append(PlotSpec("load.thrust_history", "mandatory"))
    elif intent == "body_download":
        if need(pressure_ok, "pressure semantics", "declare density / pressure dimensions"):
            sel.append(PlotSpec("pressure.static_gauge", "explanatory", "dimensional Pa"))
            sel.append(PlotSpec("traction.world_z", "mandatory", "body components"))
    elif intent == "interference":
        if need(cap.has_volume_fields and cap.velocity_frame == "absolute",
                "absolute velocity volume fields", "rerun with volume field output"):
            sel.append(PlotSpec("velocity.absolute_axial", "explanatory", "signed, diverging map"))
        sel.append(PlotSpec("load.per_rotor_delta", "mandatory"))
        rej.append("velocity magnitude as interference/thrust evidence")
    elif intent == "separation":
        if need(cap.has_wall_stress, "wall shear stress", "export wall shear stress"):
            sel.append(PlotSpec("wall_shear.signed", "explanatory", "mask undefined tangent"))
            sel.append(PlotSpec("wall_shear.vectors", "explanatory"))
        rej.append("unsigned shear magnitude as separation indicator")
    elif intent == "compressibility":
        if need(cap.has_relative_velocity, "relative velocity in rotor region",
                "export relative velocity; absolute aircraft speed is not blade Mach"):
            sel.append(PlotSpec("velocity.relative_mach", "mandatory"))
    elif intent == "numerical_quality":
        if cap.has_yplus and cap.turbulent_walls:
            sel.append(PlotSpec("mesh.y_plus", "mandatory"))
        else:
            rej.append("y plus on laminar or non-wall region")
        sel.append(PlotSpec("mesh.quality_report", "mandatory"))
        sel.append(PlotSpec("convergence.panel", "mandatory"))
    elif intent == "ground_effect":
        if need(cap.has_volume_fields, "volume fields", "rerun with volume field output"):
            sel.append(PlotSpec("velocity.absolute_axial", "explanatory", "ground clearance slice"))
        sel.append(PlotSpec("load.per_rotor_delta", "mandatory"))
    elif intent == "symmetry_comparison":
        sel.append(PlotSpec("difference.paired_component", "mandatory"))
        sel.append(PlotSpec("load.full_vs_reduced", "mandatory"))

    for f in requested:                                      # Step 4 prerequisite checks
        if f == "cp":
            if not cap.reference_speed_m_s:
                rej.append("Cp with zero reference speed (offer dimensional pressure or declared tip-speed rotor Cp)")
                sel.append(PlotSpec("pressure.static_gauge", "explanatory", "offered instead of Cp"))
            else:
                sel.append(PlotSpec("pressure.cp", "explanatory", f"q_ref from U_ref={cap.reference_speed_m_s}"))
        elif f == "blade_pressure" and not cap.has_blade_walls:
            rej.append("blade pressure: source-only rotor")
            miss.append(Missing("blade surface", "run a blade-resolved model"))
        elif f == "y_plus" and not (cap.has_yplus and cap.turbulent_walls):
            rej.append("y plus on laminar or non-wall region")
    return plan


# ------------------------------------------------------------- range policy
@dataclass(frozen=True)
class RangeRecord:
    policy: str
    vmin: float
    vmax: float
    true_min: float
    true_max: float
    clipped_fraction: float
    area_weighted: bool
    invalid_count: int


def compute_range(policy: str, fields: Sequence[np.ndarray], *, weights: Sequence[np.ndarray] | None = None,
                  percentile: float | None = None) -> RangeRecord:
    """shared_global / shared_temporal / single_full_range, optional robust percentile.
    Extrema and clipped fraction are always exposed (CT08) [M§24]."""
    if policy not in ("shared_global", "shared_temporal", "single_full_range"):
        raise ValueError(policy)
    if policy == "single_full_range" and len(fields) != 1:
        raise ValueError("single_full_range takes exactly one field")
    if not fields or not any(np.asarray(f).size for f in fields):
        raise ValueError("range requires at least one nonempty field")
    if percentile is not None and (not np.isfinite(percentile) or not 50 < percentile <= 100):
        raise ValueError("percentile must be in (50,100]")
    if weights is not None and (len(weights) != len(fields) or
            any(np.asarray(w).shape != np.asarray(f).shape for w, f in zip(weights, fields, strict=True))):
        raise ValueError("range weights must match field shapes")
    vals = np.concatenate([np.asarray(f, float).ravel() for f in fields])
    w = (np.concatenate([np.asarray(x, float).ravel() for x in weights])
         if weights is not None else np.ones_like(vals))
    if not np.isfinite(w).all() or np.any(w < 0):
        raise ValueError("range weights must be finite and nonnegative")
    finite = np.isfinite(vals)
    invalid = int((~finite).sum())
    v, w = vals[finite], w[finite]
    if not len(v) or w.sum() <= 0:
        raise ValueError("range has no finite positively weighted samples")
    tmin, tmax = float(v.min()), float(v.max())
    if percentile is None:
        lo, hi = tmin, tmax
    else:
        order = np.argsort(v)
        cw = np.cumsum(w[order]) / w.sum()
        lo = float(v[order][np.searchsorted(cw, (100 - percentile) / 100.0)])
        hi = float(v[order][min(np.searchsorted(cw, percentile / 100.0), len(v) - 1)])
    clipped = float(w[(v < lo) | (v > hi)].sum() / w.sum())
    return RangeRecord(policy, lo, hi, tmin, tmax, clipped, weights is not None, invalid)
