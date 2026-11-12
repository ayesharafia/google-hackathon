import math
from copy import deepcopy

from . import mass
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = "frozen_mass_ledger_experimental"


def _vector(value):
    _require(type(value) is list)
    _require(len(value) == 3)
    for number in value:
        _require(type(number) in (int, float))
        _normal(number)
    return tuple(float(number) for number in value)


def _preflight(request):
    _json(request, budget=16384)
    request = deepcopy(request)
    _require(type(request) is dict)
    _require(set(request) == {"evaluation", "items", "property_source"})
    _require(request["evaluation"] == EVALUATION)

    source = request["property_source"]
    _require(type(source) is str)
    _require(bool(source.strip()) and len(source) <= 2000)

    items = request["items"]
    _require(type(items) is list)
    _require(1 <= len(items) <= 128)
    names = set()
    categories = set()
    item_keys = {
        "name", "category", "mass_kg", "cg_body_m",
        "inertia_own_cg_body_kgm2",
    }
    for item in items:
        _require(type(item) is dict)
        _require(set(item) == item_keys)
        name = item["name"]
        _require(type(name) is str)
        _require(bool(name.strip()) and len(name) <= 128)
        _require(name not in names)
        names.add(name)
        category = item["category"]
        _require(type(category) is str)
        _require(category in mass.CATEGORIES)
        categories.add(category)
        mass_kg = item["mass_kg"]
        _require(type(mass_kg) in (int, float))
        _normal(mass_kg)
        _require(mass_kg >= 0)
        _vector(item["cg_body_m"])
        inertia = item["inertia_own_cg_body_kgm2"]
        _require(type(inertia) is list)
        _require(len(inertia) == 3)
        for row in inertia:
            _vector(row)

    _require(categories == set(mass.CATEGORIES))
    return request


def evaluate_mass_ledger(request):
    result = {
        "evaluation": EVALUATION,
        "status": "GRAPH_INVALID",
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "aircraft_status": None,
        "feasibility": None,
        "diagnostics_complete": False,
        "reasons": [],
        "outputs": {},
        "output_units": {},
        "limitations": [
            "Uses frozen declared mass properties.",
            "Does not infer mass from STL geometry.",
            "Does not model mass evolution or uncertainty.",
            "Does not establish physical qualification.",
            "Arithmetic behavior is that of the existing mass.summarize kernel.",
        ],
    }
    try:
        snapshot = _preflight(request)
    except Exception:  # noqa: BLE001  # Contain request/execution failures.
        result["reasons"] = ["Request preflight failed."]
        return result
    try:
        result["request_sha256"] = sha256_record(snapshot)
        entries = [
            mass.MassItem(
                name=entry["name"],
                category=entry["category"],
                mass_kg=entry["mass_kg"],
                cg_body_m=tuple(entry["cg_body_m"]),
                inertia_own_cg_body_kgm2=tuple(
                    tuple(row) for row in entry["inertia_own_cg_body_kgm2"]
                ),
            )
            for entry in snapshot["items"]
        ]
        summary = mass.summarize(entries, need_inertia=True)
        if not summary.complete:
            raise ValueError
        total = float(summary.total_mass_kg)
        cg = [float(value) for value in summary.cg_body_m.tolist()]
        inertia = [
            [float(value) for value in row]
            for row in summary.inertia_cg_body_kgm2.tolist()
        ]
        payload = float(summary.payload_kg)
        categories = {key: float(value) for key, value in summary.by_category.items()}
        if not math.isfinite(total) or total <= 0:
            raise ValueError
        if len(cg) != 3 or not all(math.isfinite(value) for value in cg):
            raise ValueError
        if len(inertia) != 3 or any(len(row) != 3 for row in inertia):
            raise ValueError
        if not all(math.isfinite(value) for row in inertia for value in row):
            raise ValueError
        if not math.isfinite(payload) or payload < 0:
            raise ValueError
        if set(categories) != set(mass.CATEGORIES):
            raise ValueError
        if any(not math.isfinite(value) or value < 0 for value in categories.values()):
            raise ValueError
        result.update(
            outputs={"total_mass_kg": total, "cg_body_m": cg,
                         "inertia_cg_body_kgm2": inertia, "payload_kg": payload,
                         "by_category_kg": categories},
            output_units={"total_mass_kg": "kg", "cg_body_m": "m",
                              "inertia_cg_body_kgm2": "kg*m^2", "payload_kg": "kg",
                              "by_category_kg": {key: "kg" for key in mass.CATEGORIES}},
            status="COMPUTED_EXPERIMENTAL", diagnostics_complete=True, reasons=[],
        )
    except Exception:  # noqa: BLE001  # Contain request/execution failures.
        result.update(status="EXECUTION_FAILED", reasons=["Mass ledger execution failed."],
                      outputs={}, output_units={}, diagnostics_complete=False)
    return result
