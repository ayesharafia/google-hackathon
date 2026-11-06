import ast
import hashlib
import importlib
import inspect
import math
import sys
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path

import pytest

from physimesh.drone.atmosphere_registry import atmosphere_catalog
from physimesh.drone.standard_atmosphere import standard_atmosphere

adapter = importlib.import_module("physimesh.drone.standard_atmosphere")
registry = sys.modules[atmosphere_catalog.__module__]
PIN = "e594cf50e0ce7d7e31cd07ee90a0d515c06b7c26f9de5a168ea8fe9af1ddd756"


def test_catalog_singleton_and_no_arguments():
    catalog = atmosphere_catalog()
    assert type(catalog) is tuple and len(catalog) == 1
    assert atmosphere_catalog() is catalog
    assert not inspect.signature(atmosphere_catalog).parameters
    with pytest.raises(TypeError):
        atmosphere_catalog(None)
    with pytest.raises(TypeError):
        atmosphere_catalog(model_id="anything")


def test_recursive_immutability():
    def visit(value):
        if is_dataclass(value):
            assert not isinstance(value, type)
            assert type(value).__dataclass_params__.frozen
            for field in fields(value):
                child = getattr(value, field.name)
                with pytest.raises(FrozenInstanceError):
                    setattr(value, field.name, child)
                visit(child)
        elif type(value) is tuple:
            for child in value:
                visit(child)
        else:
            assert type(value) in (str, int, float, bool, type(None))

    visit(atmosphere_catalog())


def test_binding_pin_contract_and_status():
    (m,) = atmosphere_catalog()
    assert m.schema_version == "atmosphere_registry_v1" and m.version == "v1"
    assert m.model_id == adapter.MODEL_ID == "coesa1976.lower-atmosphere.0-30km.v1"
    assert m.binding == adapter.__name__ + ".standard_atmosphere"
    assert (
        m.source_sha256
        == PIN
        == hashlib.sha256(Path(adapter.__file__).read_bytes()).hexdigest()
    )
    assert (m.status, m.binding_status) == ("metadata_only", "implementation_described")
    assert (m.test_evidence, m.solver_qualification, m.physical_validation) == (
        "NOT_ESTABLISHED",
    ) * 3
    assert m.execution_authorized is False
    parameters = tuple(
        inspect.signature(adapter.standard_atmosphere).parameters.values()
    )
    assert tuple(p.name for p in parameters) == tuple(v.name for v in m.inputs)
    assert tuple(p.kind for p in parameters) == (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    )
    assert all(p.default is inspect.Parameter.empty for p in parameters)
    assert tuple(f.name for f in fields(adapter.StandardAtmosphereState)) == tuple(
        v.name for v in m.outputs
    )
    assert {f.name: f.default for f in fields(adapter.StandardAtmosphereState)}[
        "model_id"
    ] == m.model_id
    assert m.input_domain == (
        ("geometric", 0.0, adapter.MAX_INPUT_ALTITUDE_M),
        ("geopotential", 0.0, adapter.MAX_INPUT_ALTITUDE_M),
    )
    assert adapter.MAX_INPUT_ALTITUDE_M == 30000.0
    assert (
        m.layers
        == adapter.LAYERS
        == ((0.0, 11000.0, -0.0065), (11000.0, 20000.0, 0.0), (20000.0, 32000.0, 0.001))
    )
    constants = {name: (value, unit) for name, value, unit, definition in m.constants}
    assert constants == {
        "Re": (adapter.EARTH_RADIUS_M, "m"),
        "g0": (adapter.G0, "m/s^2"),
        "Ru": (8314.32, "J/(kmol*K)"),
        "Mair": (28.9644, "kg/kmol"),
        "Rair": (adapter.R_AIR, "J/(kg*K)"),
    }
    assert (adapter.EARTH_RADIUS_M, adapter.G0) == (6356750.0, 9.80665)


def test_units_equations_boundaries_and_citations():
    (m,) = atmosphere_catalog()
    assert tuple(v.si_unit for v in m.inputs) == ("m", "not_applicable")
    assert tuple(v.si_unit for v in m.outputs) == (
        "m",
        "not_applicable",
        "m",
        "Pa",
        "K",
        "kg/m^3",
        "not_applicable",
        "not_applicable",
    )
    assert tuple((v.name, v.si_unit) for v in m.symbols) == (
        ("z", "m"),
        ("h", "m"),
        ("hb", "m"),
        ("Tb", "K"),
        ("pb", "Pa"),
        ("L", "K/m"),
        ("T", "K"),
        ("p", "Pa"),
        ("rho", "kg/m^3"),
    )
    for v in m.inputs + m.outputs + m.symbols:
        assert v.definition
        if v.si_unit == "not_applicable":
            assert "categorical, not a dimensionless quantity" in v.definition
    assert m.equations == (
        ("geometric_to_geopotential", "h=Re*z/(Re+z)"),
        ("geopotential_input", "h=altitude_m"),
        ("temperature", "T=Tb+L*(h-hb)"),
        ("pressure_L_nonzero", "p=pb*(T/Tb)**(-g0/(Rair*L))"),
        ("pressure_L_zero", "p=pb*exp(-g0*(h-hb)/(Rair*Tb))"),
        ("density", "rho=p/(Rair*T)"),
    )
    assert all(type(s) is str for pair in m.equations for s in pair)
    assert m.fixed_boundary_conditions == (
        ("h0", 0.0, "m"),
        ("p0", 101325.0, "Pa"),
        ("T0", 288.15, "K"),
    )
    tree = ast.parse(Path(adapter.__file__).read_text())
    initial = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Tuple)
            and tuple(getattr(e, "id", None) for e in t.elts)
            == ("pressure", "temperature")
            for t in n.targets
        )
        and isinstance(n.value, ast.Tuple)
    ]
    assert len(initial) == 1 and ast.literal_eval(initial[0].value) == (
        101325.0,
        288.15,
    )
    assert m.sources == (
        ("PDAS atmosphere definition", "https://www.pdas.com/atmosdef.html"),
        (
            "PDAS hydrostatic equations and altitude conversion",
            "https://www.pdas.com/hydro.pdf",
        ),
    )
    assert all(url in adapter.__doc__ for title, url in m.sources)
    assert (
        "Fixed sea-level boundary conditions; no caller boundary conditions"
        in m.conditions
    )


def test_registry_ast_has_only_declarative_dependencies_and_calls():
    tree = ast.parse(Path(registry.__file__).read_text())
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert len(imports) == 1
    node = imports[0]
    assert (
        isinstance(node, ast.ImportFrom)
        and node.module == "dataclasses"
        and node.level == 0
    )
    assert [(a.name, a.asname) for a in node.names] == [("dataclass", None)]
    assert not any(isinstance(n, ast.Attribute) for n in ast.walk(tree))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            assert isinstance(node.func, ast.Name) and node.func.id in {
                "dataclass",
                "Variable",
                "AtmosphereMetadata",
            }
    assert not {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} & {
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "importlib",
        "getattr",
        "globals",
        "locals",
        "read",
        "read_text",
        "read_bytes",
    }


_HYDRO_META = atmosphere_catalog()[0]
_HYDRO_C = {k: v for k, v, *_ in _HYDRO_META.constants}
_HYDRO_B = {k: v for k, v, *_ in _HYDRO_META.fixed_boundary_conditions}


def _hydro_closed(h):
    r, g = _HYDRO_C["Rair"], _HYDRO_C["g0"]
    p0, t0 = _HYDRO_B["p0"], _HYDRO_B["T0"]
    if h <= 11000:
        t = t0 - 0.0065 * h
        p = p0 * (t / t0) ** (g / (0.0065 * r))
    else:
        p11 = p0 * (216.65 / t0) ** (g / (0.0065 * r))
        if h <= 20000:
            t, p = 216.65, p11 * math.exp(-g * (h - 11000) / (r * 216.65))
        else:
            t = 216.65 + 0.001 * (h - 20000)
            p = (
                p11
                * math.exp(-g * 9000 / (r * 216.65))
                * (t / 216.65) ** (-g / (0.001 * r))
            )
    return t, p, p / (r * t)


@pytest.fixture(autouse=True)
def _hydro_qualification_guard():
    fields = (
        "status",
        "test_evidence",
        "solver_qualification",
        "physical_validation",
        "execution_authorized",
    )
    expected = (
        "metadata_only",
        "NOT_ESTABLISHED",
        "NOT_ESTABLISHED",
        "NOT_ESTABLISHED",
        False,
    )
    assert tuple(getattr(_HYDRO_META, k) for k in fields) == expected
    yield
    assert tuple(getattr(atmosphere_catalog()[0], k) for k in fields) == expected


@pytest.mark.parametrize(
    "altitude", [0, 1, 10999, 11000, 11001, 19999, 20000, 20001, 29999, 30000]
)
@pytest.mark.parametrize("kind", ["geopotential", "geometric"])
def test_hydro_closed_form(altitude, kind):
    h = (
        altitude
        if kind == "geopotential"
        else _HYDRO_C["Re"] * altitude / (_HYDRO_C["Re"] + altitude)
    )
    state = standard_atmosphere(altitude, altitude_kind=kind)
    assert (state.input_altitude_m, state.altitude_kind, state.model_id) == (
        altitude,
        kind,
        _HYDRO_META.model_id,
    )
    assert state.geopotential_altitude_m == pytest.approx(h, rel=0, abs=1e-9)
    for name, value in zip(
        ("temperature_k", "pressure_pa", "density_kg_m3"), _hydro_closed(h)
    ):
        assert getattr(state, name) == pytest.approx(value, rel=1e-12)
    assert state.evidence_status == "REFERENCE_MODEL_NOT_AIRCRAFT_VALIDATION"


def test_hydro_metadata_boundaries():
    assert _HYDRO_META.input_domain == (
        ("geometric", 0.0, 30000.0),
        ("geopotential", 0.0, 30000.0),
    )
    assert _HYDRO_META.layers == (
        (0.0, 11000.0, -0.0065),
        (11000.0, 20000.0, 0.0),
        (20000.0, 32000.0, 0.001),
    )
    assert _HYDRO_B == {"h0": 0.0, "p0": 101325.0, "T0": 288.15}
    assert _HYDRO_C["Rair"] == pytest.approx(_HYDRO_C["Ru"] / _HYDRO_C["Mair"])


@pytest.mark.parametrize("kind", ["geopotential", "geometric"])
@pytest.mark.parametrize(
    "altitude",
    [
        math.nextafter(0.0, -math.inf),
        math.nextafter(30000.0, math.inf),
        32000.0,
    ],
)
def test_hydro_exact_domain(altitude, kind):
    with pytest.raises(ValueError):
        standard_atmosphere(altitude, altitude_kind=kind)


def test_hydro_sea_level_analytic():
    state = standard_atmosphere(0, altitude_kind="geopotential")
    assert state.temperature_k == 288.15
    assert state.pressure_pa == 101325.0
    assert state.density_kg_m3 == pytest.approx(
        101325.0 / (_HYDRO_C["Rair"] * 288.15), rel=1e-12
    )


def test_hydro_independent_reference():
    # https://www.pdas.com/atmosTable1SI.html: 20 km row uses GEOMETRIC altitude.
    # Absolute tolerances reflect the last rounded table digit, not physical acceptance criteria.
    state = standard_atmosphere(20000, altitude_kind="geometric")
    assert state.temperature_k == pytest.approx(216.6, rel=0, abs=0.051)
    assert state.pressure_pa == pytest.approx(5529.0, rel=0, abs=0.51)
    assert state.density_kg_m3 == pytest.approx(0.08891, rel=0, abs=0.0000051)


def test_hydro_geometric_20km():
    hstate = standard_atmosphere(20000, altitude_kind="geopotential")
    zstate = standard_atmosphere(20000, altitude_kind="geometric")
    assert zstate.geopotential_altitude_m < hstate.geopotential_altitude_m
    assert zstate.pressure_pa > hstate.pressure_pa
    # Both lie on the isothermal plateau: temperature is correctly equal.
    assert zstate.temperature_k == pytest.approx(hstate.temperature_k)
