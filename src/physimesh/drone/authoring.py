"""Mass and pack inspection for draft authoring, independent of storage/HTTP."""
from __future__ import annotations

import math
from dataclasses import fields

from .mass import MassItem, summarize
from .screening_scope import pack_consistency


def mass_items(snapshot: dict) -> list[MassItem]:
    items = snapshot['masses']['items']
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError('masses.items must be a list of mass records')
    names = [item.get('name') for item in items]
    if any(not isinstance(name, str) or not name.strip() for name in names) or len(set(names)) != len(names):
        raise ValueError('mass item names must be meaningful and unique')
    allowed = {field.name for field in fields(MassItem)}
    for item in items:
        mass = item.get('mass_kg')
        if mass is not None and (isinstance(mass, bool) or not isinstance(mass, (int, float))):
            raise ValueError('mass must be a number in kg or null')
        cg = item.get('cg_body_m')
        if cg is not None and (not isinstance(cg, (list, tuple)) or len(cg) != 3
                               or any(v is not None and (isinstance(v, bool)
                                      or not isinstance(v, (int, float))) for v in cg)):
            raise ValueError('CG must contain three numeric metres or unknowns')
    result = []
    for item in items:
        values = {key: value for key, value in item.items() if key in allowed}
        if values.get('cg_body_m') is not None and any(v is None for v in values['cg_body_m']):
            values['cg_body_m'] = None
        result.append(MassItem(**values))
    return result


def candidate_mass(snapshot: dict, payload_kg: float, position: list[float]):
    """Replace all installed payload entries with one candidate; battery remains installed."""
    if isinstance(payload_kg, bool) or not math.isfinite(payload_kg) or payload_kg < 0:
        raise ValueError('candidate payload must be finite nonnegative kg')
    items = [item for item in mass_items(snapshot) if item.category != 'payload']
    items.append(MassItem('candidate_payload', 'payload', payload_kg, tuple(position)))
    return summarize(items)


def inspect_inputs(snapshot: dict) -> dict:
    summary = summarize(mass_items(snapshot))
    return {'mass': {'complete': summary.complete, 'total_mass_kg': summary.total_mass_kg,
                     'empty_airframe_mass_kg': summary.empty_airframe_mass_kg,
                     'installed_payload_kg': summary.payload_kg,
                     'cg_body_m': None if summary.cg_body_m is None else summary.cg_body_m.tolist(),
                     'by_category_kg': summary.by_category, 'missing': summary.missing, 'errors': summary.errors},
            'pack': pack_consistency(snapshot),
            'qualification': 'Declared-input consistency; not measured aircraft or battery validation.'}
