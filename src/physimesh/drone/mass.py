"""Mass ledger, CG and inertia. Implements [M-E01], [M-E02].

STL volume times a density is not a reliable mass estimate for a hollow assembly [M§4].
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

# Ledger categories [M§4].
CATEGORIES = ("payload", "structure", "propulsion", "energy", "avionics", "other")


@dataclass(frozen=True)
class MassItem:
    name: str
    category: str
    mass_kg: float | None
    cg_body_m: tuple | None
    inertia_own_cg_body_kgm2: tuple | None = None   # 3x3 nested tuple, already in body frame
    uncertainty_kg: float | None = None
    state: str = "fixed"            # e.g. fixed | removable_payload | consumable


@dataclass
class MassSummary:
    total_mass_kg: float | None
    cg_body_m: np.ndarray | None
    inertia_cg_body_kgm2: np.ndarray | None
    payload_kg: float | None
    by_category: dict[str, float]
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing and not self.errors

    @property
    def empty_airframe_mass_kg(self) -> float | None:
        """Known mass excluding installed payload, in kg [M-E01; USER 2026-10-02]."""
        if not self.complete or self.total_mass_kg is None or self.payload_kg is None:
            return None
        return self.total_mass_kg - self.payload_kg


def summarize(items: Sequence[MassItem], *, need_inertia: bool = False) -> MassSummary:
    """Aggregate kg, body-frame metres and kg m² [M-E01/E02].

    Payload is an observed ledger category, not a fixed design requirement
    [USER 2026-10-02: calculate payload capacity from the approved design].
    """
    missing: list[str] = []
    errors: list[str] = []
    for it in items:
        if it.category not in CATEGORIES:
            errors.append(f"masses[{it.name}].category {it.category!r} not in {CATEGORIES}")
        if it.mass_kg is None:
            missing.append(f"masses[{it.name}].mass_kg")
        elif not math.isfinite(it.mass_kg) or not it.mass_kg >= 0:
            errors.append(f"masses[{it.name}].mass_kg must be >= 0")
        if it.cg_body_m is None:
            missing.append(f"masses[{it.name}].cg_body_m")
        elif np.asarray(it.cg_body_m).shape != (3,) or not np.isfinite(it.cg_body_m).all():
            errors.append(f"masses[{it.name}].cg_body_m must be a finite 3-vector in metres")
        if it.inertia_own_cg_body_kgm2 is not None:
            own = np.asarray(it.inertia_own_cg_body_kgm2, float)
            if own.shape != (3, 3) or not np.isfinite(own).all():
                errors.append(f"masses[{it.name}].inertia must be a finite 3x3 tensor in kg m²")
            elif not np.array_equal(own, own.T) or np.linalg.eigvalsh(own).min() < 0:
                errors.append(f"masses[{it.name}].inertia must be symmetric positive semidefinite")
            else:
                moments = np.linalg.eigvalsh(own)
                # Principal moment triangle inequality [STD: rigid-body inertia identity].
                if moments[2] > moments[0] + moments[1]:
                    errors.append(f"masses[{it.name}].inertia violates principal-moment triangle inequality")
        if need_inertia and it.inertia_own_cg_body_kgm2 is None:
            missing.append(f"masses[{it.name}].inertia_own_cg_body_kgm2")
    present = {it.category for it in items}
    for cat in CATEGORIES:
        if cat not in present:
            missing.append(f"masses.{cat} (no ledger item; add an explicit 0 kg item if truly none)")
    by_cat = {c: 0.0 for c in CATEGORIES}
    if missing or errors:
        return MassSummary(None, None, None, None, by_cat, missing, errors)

    m = np.array([it.mass_kg for it in items], float)
    x = np.array([it.cg_body_m for it in items], float)
    for it in items:
        by_cat[it.category] += float(it.mass_kg)
    payload = by_cat["payload"]
    total = float(m.sum())                                          # E01
    if not np.isfinite(total) or total <= 0:
        errors.append("total mass must be finite and > 0")
        return MassSummary(None, None, None, payload, by_cat, missing, errors)
    cg = (m[:, None] * x).sum(axis=0) / total                       # E02 (CG)
    inertia = None
    if need_inertia:
        inertia = np.zeros((3, 3))
        for mj, xj, it in zip(m, x, items):
            d = xj - cg
            inertia += np.asarray(it.inertia_own_cg_body_kgm2, float) \
                + mj * (float(d @ d) * np.eye(3) - np.outer(d, d))  # E02 (parallel axis)
    if not np.isfinite(cg).all() or (inertia is not None and not np.isfinite(inertia).all()):
        errors.append("mass-derived CG or inertia overflowed")
        return MassSummary(None, None, None, payload, by_cat, missing, errors)
    return MassSummary(total, cg, inertia, payload, by_cat, missing, errors)
