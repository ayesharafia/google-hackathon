"""Mass ledger, CG and inertia. Implements [M-E01], [M-E02]."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

CATEGORIES = ("payload", "structure", "propulsion", "energy", "avionics", "other")


@dataclass(frozen=True)
class MassItem:
    name: str
    category: str
    mass_kg: Optional[float]
    cg_body_m: Optional[tuple]
    inertia_own_cg_body_kgm2: Optional[tuple] = None   # 3x3 nested tuple, already in body frame
    uncertainty_kg: Optional[float] = None
    state: str = "fixed"            # e.g. fixed | removable_payload | consumable


@dataclass
class MassSummary:
    total_mass_kg: Optional[float]
    cg_body_m: Optional[np.ndarray]
    inertia_cg_body_kgm2: Optional[np.ndarray]
    payload_kg: Optional[float]
    by_category: Dict[str, float]
    missing: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing and not self.errors


def summarize(items: Sequence[MassItem], *, required_payload_kg: float = 750.0,
              need_inertia: bool = False, payload_abs_tol_kg: float = 1e-9) -> MassSummary:
    missing: List[str] = []
    errors: List[str] = []
    for it in items:
        if it.category not in CATEGORIES:
            errors.append(f"masses[{it.name}].category {it.category!r} not in {CATEGORIES}")
        if it.mass_kg is None:
            missing.append(f"masses[{it.name}].mass_kg")
        elif not it.mass_kg >= 0:
            errors.append(f"masses[{it.name}].mass_kg must be >= 0")
        if it.cg_body_m is None:
            missing.append(f"masses[{it.name}].cg_body_m")
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
    if abs(payload - required_payload_kg) > payload_abs_tol_kg:
        errors.append(f"payload items sum to {payload} kg, requirement is {required_payload_kg} kg")
    total = float(m.sum())                                          # E01
    if total <= 0:
        errors.append("total mass must be > 0")
        return MassSummary(None, None, None, payload, by_cat, missing, errors)
    cg = (m[:, None] * x).sum(axis=0) / total                       # E02 (CG)
    inertia = None
    if need_inertia:
        inertia = np.zeros((3, 3))
        for mj, xj, it in zip(m, x, items):
            d = xj - cg
            inertia += np.asarray(it.inertia_own_cg_body_kgm2, float) \
                + mj * (float(d @ d) * np.eye(3) - np.outer(d, d))  # E02 (parallel axis)
    return MassSummary(total, cg, inertia, payload, by_cat, missing, errors)
