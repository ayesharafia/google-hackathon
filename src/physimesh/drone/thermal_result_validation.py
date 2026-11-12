"""Pure, success-only binding of actual constant-property thermal results."""

import math

from . import thermal as _thermal
from .reference_air_tabulated_hover import _exact
from .tabulated_hover_bemt_request import _json_walk, _require

# Trusted code-owned snapshots, never inferred from the caller's result.
_METADATA = {
    "model_id": _thermal.MODEL_ID, "evidence_level": "unverified",
    "aircraft_status": None, "feasibility": None,
    "limitations": list(_thermal.LIMITATIONS), "reasons": [],
    "sources": [{"url": "https://ocw.nthu.edu.tw/upload/77/news/HTchap5.pdf",
                 "scope": "Lumped energy balance, time constant, Bi<0.1 and heat generation extension"}],
}
_ROW_UNITS = {
    "index": "1", "duration_s": "s", "cumulative_elapsed_s": "s",
    "start_temperature_k": "K", "end_temperature_k": "K", "ambient_temperature_k": "K",
    "heat_input_j": "J", "thermal_storage_change_j": "J", "convective_exchange_j": "J",
    "energy_balance_residual_j": "J",
}
_OUTPUT_UNITS = {
    "segments": _ROW_UNITS, "elapsed_s": "s", "final_temperature_k": "K",
    "maximum_temperature_k": "K", "total_heat_input_j": "J",
    "total_convective_exchange_j": "J", "total_storage_change_j": "J",
    "total_energy_balance_residual_j": "J",
}
_REQUEST_FIELDS = frozenset(_thermal.FIELDS)
_SEGMENT_FIELDS = frozenset(_thermal.SEGMENT_FIELDS)
_INPUT_JSON = {
    "max_nodes_including_keys": 8192, "max_depth": 8, "max_container_items": 2048,
    "max_string_characters": 2000, "max_integer_bits": 1023, "root_depth": 1,
    "finite_floats_only": True, "valid_utf8_only": True,
}
_OUTPUT_JSON = {**_INPUT_JSON, "max_nodes_including_keys": 32768, "max_depth": 10}


def _admit(request):
    _require(type(request) is dict and request.keys() == _REQUEST_FIELDS)
    _exact(request["evaluation"], "lumped_thermal_screening")
    mass, cp, temperature, biot = map(_thermal._number, (
        request["mass_kg"], request["specific_heat_j_kg_k"],
        request["initial_temperature_k"], request["lumped_biot_number"],
    ))
    _require(min(mass, cp, temperature) > 0 and 0 <= biot <= 0.1)
    source = request["property_source"]
    _require(type(source) is str and bool(source.strip()) and len(source) <= 2000)
    capacity = _thermal.checked_product(mass, cp)
    _require(capacity > 0)
    segments = request["segments"]
    _require(type(segments) is list and 1 <= len(segments) <= 128)
    return capacity, temperature


def _arithmetic(capacity, start, ambient, heat, conductance, duration):
    """Bind the accepted binary64 operation order; no result envelope or solver."""
    product, quotient = _thermal.checked_product, _thermal.checked_quotient
    difference, finite = _thermal.checked_difference, _thermal._finite
    input_j = product(heat, duration)
    _require(heat <= 0.0 or input_j != 0.0)
    if conductance == 0.0:
        delta = quotient(input_j, capacity)
        convection = 0.0
        equilibrium = heat == 0.0
    else:
        hdt = product(conductance, duration)
        x = quotient(hdt, capacity)
        _require(x != 0.0)
        om = -math.expm1(-x)
        phi = quotient(om, x)
        if x < 1e-4:
            one_minus_phi = x * (0.5 + x * (-1.0 / 6.0 + x *
                (1.0 / 24.0 + x * (-1.0 / 120.0 + x / 720.0))))
        else:
            one_minus_phi = 1.0 - phi
        diff = difference(start, ambient)
        net = difference(heat, product(conductance, diff))
        equilibrium = net == 0.0
        delta = product(quotient(product(net, duration), capacity), phi)
        convection = finite(product(product(hdt, diff), phi) + product(input_j, one_minus_phi))
    if equilibrium:
        end = start
    elif conductance == 0.0:
        end = finite(start + delta)
    else:
        decay = finite(math.exp(-x))
        _require(decay != 0.0)
        end = finite(math.fsum((product(start, decay), product(ambient, om),
                               product(quotient(input_j, capacity), phi))))
    _require(end > 0.0)
    _require(equilibrium or (delta != 0.0 and end != start))
    storage = product(capacity, difference(end, start))
    residual = finite(finite(input_j - storage) - convection)
    return end, input_j, storage, convection, residual


def _success(actual, request):
    capacity, temperature = _admit(request)
    outputs = actual["outputs"]
    _require(type(outputs) is dict and outputs.keys() == _OUTPUT_UNITS.keys())
    rows = outputs["segments"]
    _require(type(rows) is list and len(rows) == len(request["segments"]))
    elapsed, maximum = 0.0, temperature
    for index, (row, segment) in enumerate(zip(rows, request["segments"], strict=True)):
        _require(type(segment) is dict and segment.keys() == _SEGMENT_FIELDS)
        duration, ambient, heat, conductance = map(_thermal._number, (
            segment["duration_s"], segment["ambient_temperature_k"],
            segment["heat_input_w"], segment["conductance_w_k"],
        ))
        _require(min(duration, ambient) > 0 and min(heat, conductance) >= 0)
        end, input_j, storage, convection, residual = _arithmetic(
            capacity, temperature, ambient, heat, conductance, duration,
        )
        new_elapsed = _thermal._finite(elapsed + duration)
        _require(new_elapsed > elapsed)
        _require(type(row) is dict and row.keys() == _ROW_UNITS.keys())
        for field, expected in zip(_ROW_UNITS, (
            index, duration, new_elapsed, temperature, end, ambient,
            input_j, storage, convection, residual,
        ), strict=True):
            _exact(row[field], expected)
        # The next step starts from the previous ACTUAL, fully validated endpoint.
        temperature = row["end_temperature_k"]
        elapsed = new_elapsed
        maximum = max(maximum, temperature)
    total_input = _thermal._finite(math.fsum(row["heat_input_j"] for row in rows))
    total_storage = _thermal._finite(math.fsum(row["thermal_storage_change_j"] for row in rows))
    total_convection = _thermal._finite(math.fsum(row["convective_exchange_j"] for row in rows))
    total_residual = _thermal._finite(total_input - total_storage - total_convection)
    for field, expected in (
        ("elapsed_s", elapsed), ("final_temperature_k", temperature),
        ("maximum_temperature_k", maximum), ("total_heat_input_j", total_input),
        ("total_storage_change_j", total_storage), ("total_convective_exchange_j", total_convection),
        ("total_energy_balance_residual_j", total_residual),
    ):
        _exact(outputs[field], expected)


def validate_thermal_result(actual, request):
    """Return None for a consistent actual computed result; otherwise ValueError.

    Noncomputed thermal statuses are outside this narrow admission. No model,
    integrator, runtime catalog, hash, copying hook or mutation is used.
    Unexpected pure dependency exceptions propagate.
    """
    _json_walk(actual, _OUTPUT_JSON)
    _json_walk(request, _INPUT_JSON)
    _require(type(actual) is dict and actual.keys() ==
             _METADATA.keys() | {"status", "outputs", "output_units"})
    for field, expected in _METADATA.items():
        _exact(actual[field], expected)
    _exact(actual["status"], "SCREENING_COMPUTED")
    _exact(actual["output_units"], _OUTPUT_UNITS)
    try:
        _success(actual, request)
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("Thermal arithmetic outside admitted range") from exc
