"""Unit declarations, conversions and dimension checks. SI internally [M§3]."""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

# Exact factors to metres [STD] (inch and foot are exact by definition).
LENGTH_TO_M = {"m": 1.0, "mm": 1.0e-3, "cm": 1.0e-2, "in": 0.0254, "ft": 0.3048}

# OpenFOAM dimension order: [kg m s K mol A cd] [STD, plan Task 2.2].
DIM_PRESSURE_PA: tuple[int, ...] = (1, -1, -2, 0, 0, 0, 0)
DIM_KINEMATIC_PRESSURE: tuple[int, ...] = (0, 2, -2, 0, 0, 0, 0)
DIM_VELOCITY: tuple[int, ...] = (0, 1, -1, 0, 0, 0, 0)
DIM_DENSITY: tuple[int, ...] = (1, -3, 0, 0, 0, 0, 0)


class UnitsError(ValueError):
    """An undeclared, unsupported or invalid quantity cannot be converted."""


@dataclass(frozen=True)
class ConversionRecord:
    """Retain the declared source unit and exact multiplicative SI conversion [M§3]."""

    quantity: str
    from_unit: str
    to_unit: str
    factor: float


def length_factor(unit: str | None) -> float:
    """Factor from a declared length unit to metres. Never inferred [M§11]."""
    if unit is None:
        raise UnitsError("source_units is null: declare one of "
                         + ", ".join(sorted(LENGTH_TO_M)))
    if unit not in LENGTH_TO_M:
        raise UnitsError(f"unsupported length unit {unit!r}")
    return LENGTH_TO_M[unit]


def to_si_length(values: np.ndarray, unit: str | None) -> tuple[np.ndarray, ConversionRecord]:
    """Convert finite declared lengths to metres and retain the unit conversion [M§3]."""
    f = length_factor(unit)
    array = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(array)):
        raise UnitsError("length values must be finite and supplied")
    converted = array * f
    if not np.all(np.isfinite(converted)):
        raise UnitsError("length conversion produced a non-finite value")
    return converted, ConversionRecord("length", unit, "m", f)


_DIM_RE = re.compile(r"dimensions\s*\[([^\]]*)\]\s*;")


def parse_foam_dimensions(text: str) -> tuple[int, ...]:
    """Read the `dimensions [...]` entry of an OpenFOAM field file header."""
    m = _DIM_RE.search(text)
    if not m:
        raise UnitsError("no dimensions entry found")
    try:
        vals = [float(v) for v in m.group(1).split()]
    except ValueError as error:
        raise UnitsError("invalid dimension exponent") from error
    if len(vals) not in (5, 7):
        raise UnitsError(f"expected 5 or 7 dimension exponents, got {len(vals)}")
    if any(not np.isfinite(v) or v != int(v) for v in vals):
        raise UnitsError("non-integer dimension exponent")
    ints = [int(v) for v in vals] + [0] * (7 - len(vals))
    return tuple(ints)
