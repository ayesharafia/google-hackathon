"""Versioned SI-value digest that survives browser JSON number serialization."""
import math
from collections.abc import Mapping

from physimesh.drone.provenance import sha256_record


def snapshot_sha256(record) -> str:
    """Treat 1 and 1.0 as the same number; preserve strings, null and booleans.

    Integer values above the browser's exact range are refused. This separate
    versioned scheme does not change native file hashes or canonical_json.
    """
    def normalize(value):
        if isinstance(value, Mapping):
            return {key: normalize(child) for key, child in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(child) for child in value]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value) or (isinstance(value, int) and abs(value) > 2**53):
                raise ValueError('snapshot numbers must be finite and browser-exact')
            return 0.0 if value == 0 else float(value)
        return value
    return sha256_record({'hash_scheme': 'si_numeric_snapshot_v1', 'record': normalize(record)})
