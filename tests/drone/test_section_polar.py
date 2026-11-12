"""Synthetic numerical checks, not physical validation."""

import hashlib
import json
import math
import sys
from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from physimesh.drone import section_polar as polar_module
from physimesh.drone.section_polar import EVALUATION, evaluate_section_polar, section_polar_catalog


@pytest.fixture
def request_data():
    return {
        "evaluation": EVALUATION,
        "polar": {
            "airfoil_id": "synthetic-test",
            "source": "local synthetic fixture",
            "source_kind": "synthetic",
            "uncertainty_status": "unknown",
            "sampled_mach_number": 0.1,
            "declared_mach_interval": [0, 0.3],
            "reynolds_tables": [
                {
                    "reynolds_number": 100000,
                    "rows": [{"alpha_rad": -1, "cl": -2, "cd": 0}, {"alpha_rad": 1, "cl": 2, "cd": 2}],
                },
                {
                    "reynolds_number": 400000,
                    "rows": [{"alpha_rad": -1, "cl": 0, "cd": 2}, {"alpha_rad": 1, "cl": 8, "cd": 6}],
                },
            ],
        },
        "query": {"alpha_rad": 0, "reynolds_number": 200000, "mach_number": 0.1},
    }


def test_alpha_log_re_interior(request_data):
    result = evaluate_section_polar(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    output = result["outputs"]
    assert output["cl"] == pytest.approx(2)
    assert output["cd"] == pytest.approx(2.5)
    interpolation = output["interpolation"]
    assert interpolation["alpha_weight"] == 0.5
    assert interpolation["log_reynolds_weight"] == 0.5
    assert len(interpolation["source_rows"]) == 4
    assert all(row["weight"] == 0.25 for row in interpolation["source_rows"])


def test_native_knot_single_re(request_data):
    request_data["polar"]["reynolds_tables"] = request_data["polar"]["reynolds_tables"][:1]
    row = request_data["polar"]["reynolds_tables"][0]["rows"][0]
    row.update(cl=2**53 + 1, cd=2**53 + 3)
    request_data["query"].update(alpha_rad=-1, reynolds_number=100000)
    result = evaluate_section_polar(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    for key in ("cl", "cd"):
        assert type(result["outputs"][key]) is int
        assert result["outputs"][key] == row[key]
    interp = result["outputs"]["interpolation"]
    assert interp["alpha_indices"] == interp["reynolds_indices"] == [0, 0]
    assert interp["alpha_weight"] == interp["log_reynolds_weight"] == 0
    assert len(interp["source_rows"]) == 1


@pytest.mark.parametrize("axis,value", [("alpha_rad", 2), ("reynolds_number", 500000), ("mach_number", 0.4)])
def test_out_of_each_domain(request_data, axis, value):
    request_data["query"][axis] = value
    result = evaluate_section_polar(request_data)
    assert result["status"] == "OUT_OF_POLAR_DOMAIN"
    assert result["out_of_domain_axes"] == [axis]
    assert result["outputs"] == result["output_units"] == {}
    assert result["diagnostics_complete"] is False
    assert result["request_sha256"] and result["evaluation_sha256"]


def test_single_re_no_tolerance(request_data):
    request_data["polar"]["reynolds_tables"] = request_data["polar"]["reynolds_tables"][:1]
    request_data["query"]["reynolds_number"] = math.nextafter(100000.0, math.inf)
    assert evaluate_section_polar(request_data)["status"] == "OUT_OF_POLAR_DOMAIN"


def test_mach_constant_unverified_and_source_flags(request_data):
    for kind in ("measured", "digitized_measurement", "computed", "synthetic"):
        request_data["polar"]["source_kind"] = kind
        results = []
        for mach in (0, 0.3):
            request_data["query"]["mach_number"] = mach
            result = evaluate_section_polar(request_data)
            assert result["source_classification"] == "UNVERIFIED_CALLER_ASSERTION"
            assert result["mach_interval_status"] == "UNVERIFIED_CALLER_APPLICABILITY_ONLY"
            assert result["outputs"]["mach_dependence"] == "NONE_DECLARED_APPLICABILITY_ONLY"
            results.append((result["outputs"]["cl"], result["outputs"]["cd"]))
        assert results[0] == results[1]


@pytest.mark.parametrize("value", [True, type("ForeignFloat", (float,), {})(1)])
def test_numeric_bool_subclass_rejected(request_data, value):
    request_data["query"]["alpha_rad"] = value
    result = evaluate_section_polar(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["request_sha256"] is result["evaluation_sha256"] is None


def test_catalog_fresh(request_data):
    catalog = section_polar_catalog()
    catalog["limits"]["input_json"]["max_depth"] = 0
    catalog["source_urls"].clear()
    assert section_polar_catalog()["limits"]["input_json"]["max_depth"] == 10
    assert len(section_polar_catalog()["source_urls"]) == 2
    original = deepcopy(request_data)
    evaluate_section_polar(request_data)
    assert request_data == original


def _set_path(data, path, value):
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


@pytest.mark.parametrize(
    "path,value",
    [
        (("evaluation",), True),
        (("polar", "airfoil_id"), ""),
        (("polar", "airfoil_id"), "x" * 129),
        (("polar", "source"), " \t"),
        (("polar", "source"), "x" * 2001),
        (("polar", "source"), "\ud800"),
        (("polar", "source_kind"), "as_if_computed"),
        (("polar", "uncertainty_status"), None),
        (("polar", "sampled_mach_number"), -1),
        (("polar", "sampled_mach_number"), math.inf),
        (("polar", "sampled_mach_number"), 0.4),
        (("polar", "declared_mach_interval"), [0.3, 0]),
        (("polar", "declared_mach_interval"), [0]),
        (("polar", "declared_mach_interval"), [-1, 1]),
        (("polar", "declared_mach_interval"), [0, math.inf]),
        (("polar", "reynolds_tables"), []),
        (("polar", "reynolds_tables", 0, "reynolds_number"), 0),
        (("polar", "reynolds_tables", 1, "reynolds_number"), 100000),
        (("polar", "reynolds_tables", 1, "reynolds_number"), 100),
        (("polar", "reynolds_tables", 0, "rows"), []),
        (("polar", "reynolds_tables", 0, "rows"), [{"alpha_rad": 0, "cl": 0, "cd": 0}]),
        (("polar", "reynolds_tables", 0, "rows", 0, "alpha_rad"), 2),
        (("polar", "reynolds_tables", 1, "rows", 0, "alpha_rad"), -1.0),
        (("polar", "reynolds_tables", 0, "rows", 0, "cl"), math.nan),
        (("polar", "reynolds_tables", 0, "rows", 0, "cd"), -1),
        (("query", "alpha_rad"), math.pi + 0.01),
        (("query", "alpha_rad"), math.nextafter(0.0, 1.0)),
        (("query", "reynolds_number"), math.nextafter(0.0, 1.0)),
        (("query", "mach_number"), -0.1),
        (("query", "mach_number"), math.inf),
        (("query", "reynolds_number"), 1 << 1023),
    ],
)
def test_invalid_values(request_data, path, value):
    _set_path(request_data, path, value)
    result = evaluate_section_polar(request_data)
    assert result["status"] == "MODEL_INAPPLICABLE"
    assert result["outputs"] == result["output_units"] == {}
    assert result["request_sha256"] is result["evaluation_sha256"] is None


@pytest.mark.parametrize(
    "path",
    [(), ("polar",), ("query",), ("polar", "reynolds_tables", 0), ("polar", "reynolds_tables", 0, "rows", 0)],
)
@pytest.mark.parametrize("mode", ["extra", "missing"])
def test_exact_dictionary_keys(request_data, path, mode):
    target = request_data
    for key in path:
        target = target[key]
    if mode == "extra":
        target["unexpected"] = 0
    else:
        target.pop(next(iter(target)))
    assert evaluate_section_polar(request_data)["status"] == "MODEL_INAPPLICABLE"


def _independent_digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("outside", [False, True])
def test_independent_full_hash_binding(request_data, outside):
    request_data["polar"]["source"] = "synthetic α fixture"
    if outside:
        request_data["query"]["mach_number"] = 0.4
    result = evaluate_section_polar(request_data)
    assert result["request_sha256"] == _independent_digest(request_data)
    body = {key: value for key, value in result.items() if key != "evaluation_sha256"}
    assert result["evaluation_sha256"] == _independent_digest(body)
    body["limitations"] = []
    assert result["evaluation_sha256"] != _independent_digest(body)


@pytest.mark.parametrize(
    "alpha,reynolds,count", [(-1, 100000, 1), (0, 100000, 2), (-1, 200000, 2), (0, 200000, 4)]
)
def test_unique_positive_corners(request_data, alpha, reynolds, count):
    request_data["query"].update(alpha_rad=alpha, reynolds_number=reynolds)
    result = evaluate_section_polar(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    rows = result["outputs"]["interpolation"]["source_rows"]
    assert len(rows) == len({(row["table_index"], row["row_index"]) for row in rows}) == count
    assert all(0 < row["weight"] <= 1 for row in rows)
    assert math.fsum(row["weight"] for row in rows) == pytest.approx(1)


@pytest.mark.parametrize("failure", ["lookup", "hash_first", "hash_second", "copy"])
def test_sanitized_failures(request_data, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE failure details must never appear")

    if failure == "lookup":
        monkeypatch.setattr(polar_module, "_lookup", fail)
    elif failure == "copy":
        # Fail only the initial snapshot copy; response metadata remains constructible.
        original = polar_module.deepcopy
        monkeypatch.setattr(
            polar_module, "deepcopy", lambda value: fail() if value is request_data else original(value)
        )
    else:
        original = polar_module.sha256_record
        calls = 0

        def hash_once(value):
            nonlocal calls
            calls += 1
            if calls == (1 if failure == "hash_first" else 2):
                fail()
            return original(value)

        monkeypatch.setattr(polar_module, "sha256_record", hash_once)
    result = evaluate_section_polar(request_data)
    assert result["status"] == ("MODEL_INAPPLICABLE" if failure == "copy" else "EXECUTION_FAILED")
    assert result["outputs"] == result["output_units"] == {}
    assert "PRIVATE" not in json.dumps(result)
    if failure == "hash_first":
        assert result["request_sha256"] is result["evaluation_sha256"] is None
    if failure in ("lookup", "hash_second"):
        assert result["request_sha256"] == _independent_digest(request_data)
        assert result["evaluation_sha256"] == _independent_digest(
            {key: value for key, value in result.items() if key != "evaluation_sha256"}
        )


def test_base_exception_propagates(request_data, monkeypatch):
    def interrupt(*args):
        raise KeyboardInterrupt("stop")

    monkeypatch.setattr(polar_module, "_lookup", interrupt)
    with pytest.raises(KeyboardInterrupt):
        evaluate_section_polar(request_data)


@pytest.mark.parametrize("case", ["cycle", "depth", "container", "nine_tables", "257_rows", "zero_grid"])
def test_bounded_and_grid_cases(request_data, case):
    tables = request_data["polar"]["reynolds_tables"]
    if case == "cycle":
        request_data["query"] = request_data
    elif case == "depth":
        nested = 0
        for _ in range(11):
            nested = [nested]
        request_data["query"]["alpha_rad"] = nested
    elif case == "container":
        request_data["query"]["alpha_rad"] = [0] * 257
    elif case == "nine_tables":
        request_data["polar"]["reynolds_tables"] = tables * 4 + tables[:1]
    elif case == "257_rows":
        tables[0]["rows"] = tables[0]["rows"] * 128 + tables[0]["rows"][:1]
    else:
        tables[0]["rows"][0]["alpha_rad"] = -0.0
        tables[1]["rows"][0]["alpha_rad"] = 0.0
    assert evaluate_section_polar(request_data)["status"] == "MODEL_INAPPLICABLE"


def test_all_tables_validated_before_coverage(request_data):
    request_data["query"]["mach_number"] = 100
    request_data["polar"]["reynolds_tables"][-1]["rows"][-1]["cd"] = -1
    assert evaluate_section_polar(request_data)["status"] == "MODEL_INAPPLICABLE"


def test_maximum_tables_and_rows(request_data):
    rows = [{"alpha_rad": -3.0 + 6.0 * index / 255, "cl": index, "cd": 1} for index in range(256)]
    request_data["polar"]["reynolds_tables"] = [
        {"reynolds_number": index + 1, "rows": deepcopy(rows)} for index in range(8)
    ]
    request_data["query"]["reynolds_number"] = 4
    assert evaluate_section_polar(request_data)["status"] == "COMPUTED_EXPERIMENTAL"


def test_underflow_refused_and_exact_cancellation_allowed(request_data):
    request_data["query"]["reynolds_number"] = 100000
    rows = request_data["polar"]["reynolds_tables"][0]["rows"]
    rows[0]["cd"] = sys.float_info.min
    rows[1]["cd"] = 0
    assert evaluate_section_polar(request_data)["status"] == "EXECUTION_FAILED"
    rows[0]["cd"] = rows[1]["cd"] = 0
    result = evaluate_section_polar(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    assert result["outputs"]["cl"] == 0


def test_extreme_log_ratio_and_mach_subnormal(request_data):
    tables = request_data["polar"]["reynolds_tables"]
    tables[0]["reynolds_number"] = sys.float_info.min
    tables[1]["reynolds_number"] = sys.float_info.max
    request_data["query"].update(reynolds_number=1, mach_number=math.nextafter(0.0, 1.0))
    result = evaluate_section_polar(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    weight = result["outputs"]["interpolation"]["log_reynolds_weight"]
    assert 0 < weight < 1
    assert result["outputs"]["query"]["mach_number"] == math.nextafter(0.0, 1.0)


@pytest.mark.parametrize("index", range(20))
def test_decimal95_independent_oracle(request_data, index):
    # Decimal logarithms and direct bilinear evaluation do not reuse lookup helpers.
    alpha = -0.91 + index * 0.093
    reynolds = 100001 + index * 14971
    request_data["query"].update(alpha_rad=alpha, reynolds_number=reynolds)
    result = evaluate_section_polar(request_data)
    assert result["status"] == "COMPUTED_EXPERIMENTAL"
    with localcontext() as context:
        context.prec = 95
        a = (Decimal(alpha) + 1) / 2
        r = (Decimal(reynolds) / 100000).ln() / Decimal(4).ln()
        for key in ("cl", "cd"):
            tables = request_data["polar"]["reynolds_tables"]
            corners = [Decimal(row[key]) for table in tables for row in table["rows"]]
            expected = (
                (1 - a) * (1 - r) * corners[0]
                + a * (1 - r) * corners[1]
                + (1 - a) * r * corners[2]
                + a * r * corners[3]
            )
            assert result["outputs"][key] == pytest.approx(float(expected), rel=3e-14, abs=1e-14)
        assert result["outputs"]["interpolation"]["log_reynolds_weight"] == pytest.approx(float(r), rel=5e-15)


def test_interior_endpoint_collapse_fails_closed(request_data):
    # Native integer Re is strictly interior but converts to the upper binary64 endpoint.
    base = 2**53
    request_data["polar"]["reynolds_tables"][0]["reynolds_number"] = base
    request_data["polar"]["reynolds_tables"][1]["reynolds_number"] = base + 4
    request_data["query"]["reynolds_number"] = base + 3
    result = evaluate_section_polar(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["outputs"] == {}
    assert result["request_sha256"] and result["evaluation_sha256"]


@pytest.mark.parametrize(
    "alpha,expected",
    [(math.nextafter(-1.0, 0), "COMPUTED_EXPERIMENTAL"), (math.nextafter(1.0, 0), "EXECUTION_FAILED")],
)
def test_nextafter_alpha_remains_interior(request_data, alpha, expected):
    request_data["query"].update(alpha_rad=alpha, reynolds_number=100000)
    result = evaluate_section_polar(request_data)
    assert result["status"] == expected
    if expected == "EXECUTION_FAILED":
        assert result["outputs"] == {}
        return
    interpolation = result["outputs"]["interpolation"]
    assert interpolation["alpha_indices"] == [0, 1]
    assert 0 < interpolation["alpha_weight"] < 1
    assert len(interpolation["source_rows"]) == 2


def test_signed_zero_native_and_copy_isolation(request_data):
    request_data["query"].update(alpha_rad=-1, reynolds_number=100000)
    request_data["polar"]["reynolds_tables"][0]["rows"][0].update(cl=-0.0, cd=-0.0)
    result = evaluate_section_polar(request_data)
    for key in ("cl", "cd"):
        assert type(result["outputs"][key]) is float
        assert math.copysign(1, result["outputs"][key]) == -1
    result["outputs"]["query"]["alpha_rad"] = 2
    result["outputs"]["declared_mach_interval"].clear()
    result["outputs"]["interpolation"]["source_rows"][0]["cl"] = 7
    result["limits"]["input_json"]["max_depth"] = 0
    fresh = evaluate_section_polar(request_data)
    assert fresh["outputs"]["query"]["alpha_rad"] == -1
    assert fresh["outputs"]["declared_mach_interval"] == [0, 0.3]
    assert math.copysign(1, fresh["outputs"]["cl"]) == -1
    assert fresh["limits"]["input_json"]["max_depth"] == 10


def test_persistent_hash_failure_sanitized(request_data, monkeypatch):
    def fail(*args):
        raise RuntimeError("PRIVATE persistent hash failure")

    monkeypatch.setattr(polar_module, "sha256_record", fail)
    result = evaluate_section_polar(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] is result["evaluation_sha256"] is None
    assert "PRIVATE" not in json.dumps(result)


def test_persistent_seal_hash_failure_drops_both_hashes(request_data, monkeypatch):
    original = polar_module.sha256_record

    def fail_response(value):
        if "request_sha256" in value:
            raise RuntimeError("PRIVATE seal failure")
        return original(value)

    monkeypatch.setattr(polar_module, "sha256_record", fail_response)
    result = evaluate_section_polar(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["request_sha256"] is result["evaluation_sha256"] is None
    assert result["outputs"] == {}


@pytest.mark.parametrize("bad_output", ["x" * 2001, [0] * 257, {"private": float("nan")}])
def test_postexport_bounds_sanitized(request_data, monkeypatch, bad_output):
    monkeypatch.setattr(polar_module, "_lookup", lambda *args: bad_output)
    result = evaluate_section_polar(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["outputs"] == result["output_units"] == {}


def test_status_matrix_and_unsupported_root(request_data):
    catalog = section_polar_catalog()
    assert set(catalog["status_matrix"]) == {
        "RESEARCH_ONLY",
        "MODEL_INAPPLICABLE",
        "SOLVER_UNSUPPORTED",
        "OUT_OF_POLAR_DOMAIN",
        "COMPUTED_EXPERIMENTAL",
        "EXECUTION_FAILED",
    }
    request_data["evaluation"] = "another_local_lookup"
    assert evaluate_section_polar(request_data)["status"] == "SOLVER_UNSUPPORTED"
    request_data["extra"] = 0
    assert evaluate_section_polar(request_data)["status"] == "MODEL_INAPPLICABLE"


@pytest.mark.parametrize("output", [False, True])
def test_exact_walk_node_and_depth_budgets(output):
    count = 32 if output else 128
    at_limit = [[0] * 255 for _ in range(count)]
    at_limit[-1].pop()
    polar_module._walk(at_limit, output=output)
    at_limit[-1].append(0)
    with pytest.raises(ValueError):
        polar_module._walk(at_limit, output=output)
    nested = 0
    for _ in range(11 if output else 9):
        nested = [nested]
    polar_module._walk(nested, output=output)
    with pytest.raises(ValueError):
        polar_module._walk([nested], output=output)


@pytest.mark.parametrize(
    "path,key",
    [
        ((), "evaluation"),
        ((), "polar"),
        ((), "query"),
        (("polar",), "airfoil_id"),
        (("polar",), "source"),
        (("polar",), "source_kind"),
        (("polar",), "uncertainty_status"),
        (("polar",), "sampled_mach_number"),
        (("polar",), "declared_mach_interval"),
        (("polar",), "reynolds_tables"),
        (("query",), "alpha_rad"),
        (("query",), "reynolds_number"),
        (("query",), "mach_number"),
        (("polar", "reynolds_tables", 0), "reynolds_number"),
        (("polar", "reynolds_tables", 0), "rows"),
        (("polar", "reynolds_tables", 0, "rows", 0), "alpha_rad"),
        (("polar", "reynolds_tables", 0, "rows", 0), "cl"),
        (("polar", "reynolds_tables", 0, "rows", 0), "cd"),
    ],
)
def test_each_required_key_missing(request_data, path, key):
    target = request_data
    for field in path:
        target = target[field]
    target.pop(key)
    assert evaluate_section_polar(request_data)["status"] == "MODEL_INAPPLICABLE"


def test_checked_primitive_failure(request_data, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("PRIVATE numeric primitive")

    monkeypatch.setattr(polar_module, "_normal", fail)
    result = evaluate_section_polar(request_data)
    assert result["status"] == "EXECUTION_FAILED"
    assert result["outputs"] == {}
    assert "PRIVATE" not in json.dumps(result)


def test_maximum_request_actual_node_count(request_data):
    rows = [{"alpha_rad": -3.0 + 6.0 * index / 255, "cl": index, "cd": 1} for index in range(256)]
    request_data["polar"]["reynolds_tables"] = [
        {"reynolds_number": index + 1, "rows": deepcopy(rows)} for index in range(8)
    ]
    request_data["query"]["reynolds_number"] = 4

    def nodes(value):
        if type(value) is dict:
            return 1 + sum(nodes(key) + nodes(child) for key, child in value.items())
        if type(value) is list:
            return 1 + sum(nodes(child) for child in value)
        return 1

    count = nodes(request_data)
    assert 14000 < count < 32768
    assert evaluate_section_polar(request_data)["status"] == "COMPUTED_EXPERIMENTAL"
