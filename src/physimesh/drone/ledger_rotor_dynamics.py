import math
from copy import deepcopy

from . import mass_ledger_request as ml
from . import rotor_fixed_load_dynamics as fd
from .rotor_fixed_load_dynamics import (
    _json,
    _normal,
    sha256_record,
)
from .rotor_fixed_load_dynamics import (
    _require as _base_require,
)

EVALUATION = "ledger_rotor_frozen_load_dynamics_experimental"


def _require(condition, reason=None):
    _base_require(condition)


def _dynamics_input(s, massoutputs):
    assembly = deepcopy(s["assembly_template"])
    assembly["mass_kg"] = deepcopy(massoutputs["total_mass_kg"])
    assembly["cg_body_m"] = deepcopy(massoutputs["cg_body_m"])
    return {
        "evaluation": fd.EVALUATION,
        "assembly": assembly,
        "inertia_body_kg_m2": deepcopy(
            massoutputs["inertia_cg_body_kgm2"]
        ),
        "initial_state": deepcopy(s["initial_state"]),
        "dt_s": deepcopy(s["dt_s"]),
        "steps": deepcopy(s["steps"]),
        "applicability_declaration": deepcopy(
            s["applicability_declaration"]
        ),
    }


def _preflight(req):
    _json(req, budget=49152)
    _require(isinstance(req, dict), "request must be an object")
    _require(
        set(req) == {
            "evaluation", "ledger", "assembly_template",
            "initial_state", "dt_s", "steps",
            "applicability_declaration",
        },
        "request has invalid keys",
    )
    _require(req["evaluation"] == EVALUATION, "invalid evaluation")
    ml._preflight(req["ledger"])

    template = req["assembly_template"]
    _require(isinstance(template, dict), "assembly_template must be an object")
    _require(
        set(template) == {
            "evaluation", "graph", "air_node", "rotors",
            "gravity_direction_body", "property_source",
        },
        "assembly_template has invalid keys",
    )
    snapshot = deepcopy(req)
    structural_placeholder = {
        "total_mass_kg": 1,
        "cg_body_m": [0, 0, 0],
        "inertia_cg_body_kgm2": [
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
        ],
    }
    fd._preflight(_dynamics_input(snapshot, structural_placeholder))
    return snapshot


def _valid(raw, evaluation, request):
    _json(raw, budget=65536, items=2048)
    _require(type(raw) is dict, "result must be a builtin dict")
    _require("evaluation" in raw and raw["evaluation"] == evaluation,
             "evaluation mismatch")
    _require(raw.get("status") == "COMPUTED_EXPERIMENTAL", "invalid status")
    _require(raw.get("diagnostics_complete") is True,
             "diagnostics must be complete")
    reasons = raw.get("reasons")
    _require(type(reasons) is list and len(reasons) == 0,
             "reasons must be an empty builtin list")
    _require(raw.get("evidence_level") == "unverified", "invalid evidence level")
    for field in ("physical_validation", "numerical_qualification", "runtime_identity"):
        _require(raw.get(field) == "NOT_ESTABLISHED", "invalid " + field)
    for field in ("feasibility", "aircraft_status"):
        _require(field in raw and raw[field] is None, field + " must be None")
    _require(raw.get("request_sha256") == sha256_record(request),
             "request hash mismatch")
    _require(type(raw.get("outputs")) is dict, "outputs must be a builtin dict")
    _require(type(raw.get("output_units")) is dict,
             "output_units must be a builtin dict")


def _ledger_outputs(raw):
    _require(type(raw) is dict, "result must be a builtin dict")
    outputs = raw.get("outputs")
    units = raw.get("output_units")
    keys = {"total_mass_kg", "cg_body_m", "inertia_cg_body_kgm2",
            "payload_kg", "by_category_kg"}
    categories = set(ml.mass.CATEGORIES)
    _require(type(outputs) is dict and set(outputs) == keys,
             "invalid output keys")
    _require(type(units) is dict, "output_units must be a builtin dict")
    _require(type(units.get("by_category_kg")) is dict,
             "category units must be a builtin dict")
    _require(units == {
        "total_mass_kg": "kg",
        "cg_body_m": "m",
        "inertia_cg_body_kgm2": "kg*m^2",
        "payload_kg": "kg",
        "by_category_kg": {category: "kg" for category in categories},
    }, "invalid output units")
    total = outputs["total_mass_kg"]
    _require(type(total) in (int, float) and total > 0 and _normal(total),
             "invalid total mass")
    cg = outputs["cg_body_m"]
    _require(type(cg) is list and len(cg) == 3, "invalid CG shape")
    for value in cg:
        _require(type(value) in (int, float) and _normal(value) is not None, "invalid CG value")
    inertia = outputs["inertia_cg_body_kgm2"]
    _require(type(inertia) is list and len(inertia) == 3, "invalid inertia shape")
    for row in inertia:
        _require(type(row) is list and len(row) == 3, "invalid inertia row")
        for value in row:
            _require(type(value) in (int, float) and _normal(value) is not None,
                     "invalid inertia value")
    by_category = outputs["by_category_kg"]
    _require(type(by_category) is dict and set(by_category) == categories,
             "invalid mass categories")
    for value in [outputs["payload_kg"], *by_category.values()]:
        _require(type(value) in (int, float) and value >= 0
                 and (type(value) is int or math.isfinite(value)),
                 "mass must be finite and nonnegative")
    return deepcopy(outputs)


def _validated_frozen(raw, request):
    _require(type(raw) is dict, "frozen result must be a builtin dict")
    for field in ("outputs", "output_units"):
        value = raw.get(field)
        _require(
            type(value) is dict and set(value) == {"assembly", "dynamics"},
            f"{field} must have exactly assembly and dynamics keys",
        )

    assembly_hash = sha256_record(request["assembly"])
    assembly_raw = deepcopy(raw)
    assembly_raw["evaluation"] = fd.ra.EVALUATION
    assembly_raw["request_sha256"] = assembly_hash
    assembly_raw["outputs"] = raw["outputs"]["assembly"]
    assembly_raw["output_units"] = raw["output_units"]["assembly"]
    force, moment, gravity = fd._assembly_loads(
        assembly_raw, request["assembly"]
    )

    rigid_input = {
        "evaluation": "rigid_body_constant_wrench_experimental",
        "initial_state": request["initial_state"],
        "mass_kg": request["assembly"]["mass_kg"],
        "inertia_body_kg_m2": request["inertia_body_kg_m2"],
        "force_body_n": list(force),
        "moment_cg_body_nm": list(moment),
        "gravity_enu_m_s2": list(gravity),
        "dt_s": request["dt_s"],
        "steps": request["steps"],
        "property_source": request["assembly"]["property_source"],
        "applicability_declaration": request["applicability_declaration"],
    }
    fd._validated_dynamics(
        {
            "reasons": [],
            # Fixed guard placeholder, not recovered upstream metadata or evidence.
            # Required solely for the accepted output numeric validator's shape.
            "inertia_physical_admissibility": "NOT_ASSESSED",
            "outputs": raw["outputs"]["dynamics"],
            "output_units": raw["output_units"]["dynamics"],
        },
        rigid_input,
    )
    expected_transfers = {
        "force_body_n": list(force),
        "moment_cg_body_nm": list(moment),
        "gravity_enu_m_s2": list(gravity),
    }
    transfers = raw.get("transfers")
    _require(
        type(transfers) is dict and transfers == expected_transfers,
        "transfers must exactly match validated assembly loads",
    )

    stages = raw.get("stages")
    _require(type(stages) is list and len(stages) == 2, "stages must be a builtin list of length 2")
    expected_stages = (("assembly", assembly_hash), ("dynamics", sha256_record(rigid_input)))
    for stage, (stage_id, request_hash) in zip(stages, expected_stages):
        _require(
            type(stage) is dict and set(stage) == {"stage_id", "request_sha256", "result_sha256"},
            "each stage must be a builtin dict with exactly the required keys",
        )
        _require(stage["stage_id"] == stage_id, "stage IDs must be assembly then dynamics")
        _require(stage["request_sha256"] == request_hash, "stage request hash mismatch")
        result_hash = stage["result_sha256"]
        _require(
            type(result_hash) is str and len(result_hash) == 64
            and all(char in "0123456789abcdef" for char in result_hash),
            "stage result hash must be a 64-character lowercase hexadecimal string",
        )


def evaluate_ledger_rotor_dynamics(request):
    result = {
        "status": "GRAPH_INVALID",
        "evaluation": EVALUATION,
        "evidence_level": "unverified",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "feasibility": None,
        "aircraft_status": None,
        "diagnostics_complete": False,
        "reasons": [],
        "stages": [],
        "transfers": {},
        "outputs": {},
        "output_units": {},
        "limitations": [
            "Frozen ledger snapshot; no mass evolution.",
            "Common caller-declared body axes.",
            "Isolated frozen rotor loads with raw-stage RK4.",
            "No installed-flight, trim, control, or stability assessment.",
            "No energy or thermal assessment.",
            "No physical validation or numerical qualification.",
        ],
    }
    try:
        s = _preflight(request)
        request_sha256 = sha256_record(s)
    except Exception:  # noqa: BLE001 - contain all preflight failures.
        result["reasons"] = ["Request preflight failed."]
        return deepcopy(result)

    result["request_sha256"] = request_sha256
    try:
        lr = ml.evaluate_mass_ledger(s["ledger"])
        _valid(lr, ml.EVALUATION, s["ledger"])
        o = _ledger_outputs(lr)
        di = _dynamics_input(s, o)
        dr = fd.evaluate_rotor_fixed_load_dynamics(di)
        _valid(dr, fd.EVALUATION, di)
        _validated_frozen(dr, di)
        success = {
            "status": "COMPUTED_EXPERIMENTAL",
            "diagnostics_complete": True,
            "stages": [
                {
                    "stage_id": "ledger",
                    "request_sha256": sha256_record(s["ledger"]),
                    "result_sha256": sha256_record(lr),
                },
                {
                    "stage_id": "frozen_dynamics",
                    "request_sha256": sha256_record(di),
                    "result_sha256": sha256_record(dr),
                },
            ],
            "transfers": {
                "mass_kg": o["total_mass_kg"],
                "cg_body_m": o["cg_body_m"],
                "inertia_body_kg_m2": o["inertia_cg_body_kgm2"],
            },
            "outputs": {"ledger": lr["outputs"], "frozen_dynamics": dr["outputs"]},
            "output_units": {
                "ledger": lr["output_units"],
                "frozen_dynamics": dr["output_units"],
            },
        }
        success = deepcopy(success)
    except Exception:  # noqa: BLE001 - contain all execution failures.
        result["status"] = "EXECUTION_FAILED"
        result["reasons"] = ["Evaluation execution failed."]
        return deepcopy(result)

    result.update(success)
    return deepcopy(result)
