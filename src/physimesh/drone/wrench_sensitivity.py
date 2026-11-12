import itertools
from copy import deepcopy

import numpy as np

from . import rotor_assembly as ra
from . import static_wrench_solve as ws
from .graph_mission import _normal, _require
from .model_graph_execution import _json
from .provenance import sha256_record

EVALUATION = "static_wrench_sensitivity_experimental"


def _preflight(request):
    _json(request, budget=32768)
    s = deepcopy(request)
    _require(type(s) is dict)
    _require(set(s) == {
        "evaluation", "assembly", "perturbations", "force_scale_n",
        "moment_scale_nm", "relative_singular_value_cutoff",
    })
    _require(s["evaluation"] == EVALUATION)
    s["assembly"] = ra._preflight(s["assembly"])
    assembly = s["assembly"]
    rotors = assembly["rotors"]
    n = len(rotors)
    _require(1 <= n <= 15)
    _require(type(s["perturbations"]) is list)
    _require(len(s["perturbations"]) == n)
    _require(_normal(s["force_scale_n"]) > 0)
    _require(_normal(s["moment_scale_nm"]) > 0)
    cutoff = _normal(s["relative_singular_value_cutoff"])
    _require(0 < cutoff < 1)
    planned_calls = 1 + 6 * n
    _require(planned_calls <= 91)
    nodes = {node["id"]: node for node in assembly["graph"]["nodes"]}
    total_annuli = 0
    for rotor, perturbation in zip(rotors, s["perturbations"]):
        _require(type(perturbation) is dict)
        _require(set(perturbation) == {
            "node", "half_step_rad_s", "speed_scale_rad_s",
        })
        _require(perturbation["node"] == rotor["node"])
        node = nodes[rotor["node"]]
        _require(node["model"] == "isolated_hover_bemt_experimental")
        inputs = node["inputs"]
        annuli = inputs["annuli"]
        _require(type(annuli) is int)
        _require(1 <= annuli <= 512)
        total_annuli += annuli
        omega = _normal(inputs["angular_speed_rad_s"])
        _require(omega > 0)
        h = _normal(perturbation["half_step_rad_s"])
        _require(h > 0)
        _require(_normal(perturbation["speed_scale_rad_s"]) > 0)
        _require(_normal(2 * h) > 0)
        samples = [omega]
        for level in range(3):
            step = h / (2 ** level)
            plus = _normal(omega + step)
            minus = _normal(omega - step)
            _require(plus > 0 and minus > 0)
            _require(plus > omega > minus)
            samples.extend((plus, minus))
        _require(len(set(samples)) == 7)
    _require(total_annuli * planned_calls <= 32768)
    return s


def _perturbed(s, index, delta):
    assembly = deepcopy(s["assembly"])
    rotor_node = assembly["rotors"][index]["node"]
    node = next(
        node for node in assembly["graph"]["nodes"]
        if node["id"] == rotor_node
    )
    node["inputs"]["angular_speed_rad_s"] += delta
    return assembly


def _level(s, pairs, steps):
    perturbations = s["perturbations"]
    n = len(perturbations)
    _require(type(pairs) is list and type(steps) is list)
    _require(1 <= n <= 15 and len(pairs) == n and len(steps) == n)

    force_scale = _normal(s["force_scale_n"])
    moment_scale = _normal(s["moment_scale_nm"])
    relative_cutoff = _normal(s["relative_singular_value_cutoff"])
    _require(force_scale > 0)
    _require(moment_scale > 0)
    _require(0 < relative_cutoff < 1)

    for perturbation, step in zip(perturbations, steps):
        speed_scale = _normal(perturbation["speed_scale_rad_s"])
        _normal(step)
        _require(speed_scale > 0)
        _require(step > 0)

    columns, dimensionless_columns = [], []
    for pair, step, perturbation in zip(pairs, steps, perturbations):
        denominator = _normal(2 * step)
        _require(denominator > 0)
        plus, minus = pair
        plus_outputs, minus_outputs = plus["outputs"], minus["outputs"]
        column = []

        for key in ("net_force_body_n", "net_moment_cg_body_nm"):
            positive, negative = plus_outputs[key], minus_outputs[key]
            _require(type(positive) is list and type(negative) is list)
            _require(len(positive) == 3 and len(negative) == 3)
            for p, m in zip(positive, negative):
                _normal(p)
                _normal(m)
                difference = _normal(p - m)
                derivative = _normal(difference / denominator)
                column.append(derivative)

        scaled_column = []
        for row, derivative in enumerate(column):
            scale = force_scale if row < 3 else moment_scale
            numerator = _normal(
                derivative * perturbation["speed_scale_rad_s"]
            )
            value = _normal(numerator / scale)
            scaled_column.append(value)

        columns.append(column)
        dimensionless_columns.append(scaled_column)

    jacobian = [[column[row] for column in columns] for row in range(6)]
    dimensionless = [
        [column[row] for column in dimensionless_columns] for row in range(6)
    ]

    raw_sv = np.linalg.svd(dimensionless, compute_uv=False)
    singular_values = []
    for raw_value in raw_sv:
        value = _normal(float(raw_value))
        _require(value >= 0)
        singular_values.append(value)

    cutoff = _normal(relative_cutoff * singular_values[0])
    _require(cutoff >= 0)

    return {
        "half_steps_rad_s": list(steps),
        "force_jacobian_n_per_rad_s": jacobian[:3],
        "moment_jacobian_nm_per_rad_s": jacobian[3:],
        "dimensionless_jacobian": dimensionless,
        "singular_values": singular_values,
        "numerical_rank": sum(value > cutoff for value in singular_values),
        "rank_cutoff": cutoff,
    }


def _changes(levels):
    _require(len(levels) == 3)
    changes = []
    for previous, current in itertools.pairwise(levels):
        change = {}
        for output, key in (
            ("force_max_abs_delta", "force_jacobian_n_per_rad_s"),
            ("moment_max_abs_delta", "moment_jacobian_nm_per_rad_s"),
            ("dimensionless_max_abs_delta", "dimensionless_jacobian"),
        ):
            maximum = 0.0
            for old_row, new_row in zip(previous[key], current[key]):
                for old, new in zip(old_row, new_row):
                    _normal(old)
                    _normal(new)
                    difference = _normal(new - old)
                    delta = _normal(abs(difference))
                    maximum = max(maximum, delta)
            change[output] = maximum
        changes.append(change)
    return changes


def evaluate_wrench_sensitivity(request):
    envelope = {
        "evaluation": "static_wrench_sensitivity_experimental",
        "status": "GRAPH_INVALID",
        "physical_validation": "NOT_ESTABLISHED",
        "numerical_qualification": "NOT_ESTABLISHED",
        "runtime_identity": "NOT_ESTABLISHED",
        "evidence_level": "unverified",
        "aircraft_status": None,
        "feasibility": None,
        "diagnostics_complete": False,
        "reasons": [],
        "stages": [],
        "outputs": {},
        "output_units": {},
        "limitations": [
            ("Local derivatives and numerical rank do not establish physical trim, "
            "control authority, stability, or feasibility."),
            ("Scales and the singular-value cutoff are caller-selected diagnostic "
            "choices; rank deficiency does not establish global infeasibility."),
            ("Changes across three finite-difference resolutions provide neither "
            "an error certificate nor proof of convergence."),
            "Every probe is an actual fresh assembly evaluation using common air inputs.",
            ("The isolated-rotor, small-angle assumptions remain; no rotor interference "
            "or new physics is introduced."),
            ("Inner graph result_sha256 fields are checked for syntax only; each stage "
            "result_sha256 hashes the whole actual raw assembly result and does not "
            "establish qualification."),
            "Zero-speed and failed-rotor cases are unsupported.",
        ],
    }
    try:
        s = _preflight(request)
        request_hash = sha256_record(s)
    except Exception:  # noqa: BLE001
        envelope["reasons"] = ["Invalid wrench sensitivity request."]
        return deepcopy(envelope)
    envelope["request_sha256"] = request_hash

    def run(req, stage_id):
        input_hash = sha256_record(req)
        raw = ra.evaluate_rotor_assembly(req)
        ws._assembly_contract(raw, req)
        envelope["stages"].append({
            "stage_id": stage_id,
            "request_sha256": input_hash,
            "result_sha256": sha256_record(raw),
        })
        return raw

    try:
        nominal = run(s["assembly"], "nominal")
        rotor_nodes = [rotor["node"] for rotor in s["assembly"]["rotors"]]
        levels = []
        for k in range(3):
            pairs, steps = [], []
            for i, perturbation in enumerate(s["perturbations"]):
                node = perturbation["node"]
                delta = perturbation["half_step_rad_s"] / (2 ** k)
                plus = run(_perturbed(s, i, delta), f"level_{k}_rotor_{node}_plus")
                minus = run(_perturbed(s, i, -delta), f"level_{k}_rotor_{node}_minus")
                pairs.append((plus, minus))
                steps.append(delta)
            levels.append(_level(s, pairs, steps))
        changes = _changes(levels)
        _require(len(envelope["stages"]) == 1 + 6 * len(rotor_nodes))
        envelope["outputs"] = {
            "nominal_assembly": nominal["outputs"],
            "rotor_nodes": rotor_nodes,
            "evaluations_used": len(envelope["stages"]),
            "levels": levels,
            "changes": changes,
        }
        envelope["output_units"] = {
            "nominal_assembly": nominal["output_units"],
            "rotor_nodes": "not_applicable",
            "evaluations_used": "1",
            "levels": [{
                "half_steps_rad_s": "rad/s",
                "force_jacobian_n_per_rad_s": "N/(rad/s)",
                "moment_jacobian_nm_per_rad_s": "N*m/(rad/s)",
                "dimensionless_jacobian": "1",
                "singular_values": "1",
                "numerical_rank": "1",
                "rank_cutoff": "1",
            } for _ in range(3)],
            "changes": [{
                "force_max_abs_delta": "N/(rad/s)",
                "moment_max_abs_delta": "N*m/(rad/s)",
                "dimensionless_max_abs_delta": "1",
            } for _ in range(2)],
        }
        envelope["status"] = "COMPUTED_EXPERIMENTAL"
        envelope["diagnostics_complete"] = True
    except Exception:  # noqa: BLE001
        envelope["status"] = "EXECUTION_FAILED"
        envelope["diagnostics_complete"] = False
        envelope["reasons"] = ["Wrench sensitivity evaluation failed."]
        envelope["stages"] = []
        envelope["outputs"] = {}
        envelope["output_units"] = {}
    return deepcopy(envelope)
