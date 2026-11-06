"""Immutable descriptive metadata; no model execution or caller registration."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Variable:
    name: str
    si_unit: str
    definition: str


@dataclass(frozen=True, slots=True)
class AtmosphereMetadata:
    schema_version: str
    model_id: str
    version: str
    binding: str
    binding_status: str
    source_sha256: str
    inputs: tuple[Variable, ...]
    outputs: tuple[Variable, ...]
    altitude_reference: tuple[str, ...]
    input_domain: tuple[tuple[str, float, float], ...]
    symbols: tuple[Variable, ...]
    constants: tuple[tuple[str, float, str, str], ...]
    layers: tuple[tuple[float, float, float], ...]
    layer_convention: str
    equations: tuple[tuple[str, str], ...]
    fixed_boundary_conditions: tuple[tuple[str, float, str], ...]
    conditions: tuple[str, ...]
    sources: tuple[tuple[str, str], ...]
    status: str
    test_evidence: str
    solver_qualification: str
    physical_validation: str
    execution_authorized: bool
    limitations: tuple[str, ...]


_CATALOG = (
    AtmosphereMetadata(
        schema_version="atmosphere_registry_v1",
        model_id="coesa1976.lower-atmosphere.0-30km.v1",
        version="v1",
        binding="physimesh.drone.standard_atmosphere.standard_atmosphere",
        binding_status="implementation_described",
        source_sha256="e594cf50e0ce7d7e31cd07ee90a0d515c06b7c26f9de5a168ea8fe9af1ddd756",
        inputs=(
            Variable(
                "altitude_m",
                "m",
                "Finite scalar geometric z or geopotential h; bool excluded",
            ),
            Variable(
                "altitude_kind",
                "not_applicable",
                "Required: geometric or geopotential; categorical, not a dimensionless quantity",
            ),
        ),
        outputs=(
            Variable("input_altitude_m", "m", "Input scalar altitude"),
            Variable(
                "altitude_kind",
                "not_applicable",
                "Input altitude convention; categorical, not a dimensionless quantity",
            ),
            Variable("geopotential_altitude_m", "m", "Geopotential altitude h"),
            Variable("pressure_pa", "Pa", "Absolute pressure p"),
            Variable("temperature_k", "K", "Absolute temperature T"),
            Variable("density_kg_m3", "kg/m^3", "Dry-air mass density rho"),
            Variable(
                "model_id",
                "not_applicable",
                "Fixed model identifier; categorical, not a dimensionless quantity",
            ),
            Variable(
                "evidence_status",
                "not_applicable",
                "REFERENCE_MODEL_NOT_AIRCRAFT_VALIDATION; categorical, not a dimensionless quantity",
            ),
        ),
        altitude_reference=(
            "Scalar reference altitude above standard sea-level datum",
            "Geometric z or geopotential h; no terrain-relative interpretation",
        ),
        input_domain=(("geometric", 0.0, 30000.0), ("geopotential", 0.0, 30000.0)),
        symbols=(
            Variable("z", "m", "Geometric altitude above standard sea-level datum"),
            Variable(
                "h", "m", "Geopotential altitude; equals input for geopotential kind"
            ),
            Variable("hb", "m", "Current geopotential layer base altitude"),
            Variable("Tb", "K", "Temperature at hb, advanced from preceding layer"),
            Variable(
                "pb", "Pa", "Absolute pressure at hb, advanced from preceding layer"
            ),
            Variable("L", "K/m", "Current layer temperature gradient"),
            Variable("T", "K", "Temperature at h"),
            Variable("p", "Pa", "Absolute pressure at h"),
            Variable("rho", "kg/m^3", "Dry-air density at h"),
        ),
        constants=(
            (
                "Re",
                6356750.0,
                "m",
                "Hydrostatic altitude-conversion radius; not terrain radius",
            ),
            ("g0", 9.80665, "m/s^2", "Standard gravitational acceleration"),
            ("Ru", 8314.32, "J/(kmol*K)", "Source universal gas constant"),
            ("Mair", 28.9644, "kg/kmol", "Source dry-air molar mass"),
            (
                "Rair",
                8314.32 / 28.9644,
                "J/(kg*K)",
                "Ru/Mair; source expression 8314.32/28.9644",
            ),
        ),
        layers=(
            (0.0, 11000.0, -0.0065),
            (11000.0, 20000.0, 0.0),
            (20000.0, 32000.0, 0.001),
        ),
        layer_convention="(hb, top, L): geopotential m, geopotential m, K/m; 32000 is not an input extension",
        equations=(
            ("geometric_to_geopotential", "h=Re*z/(Re+z)"),
            ("geopotential_input", "h=altitude_m"),
            ("temperature", "T=Tb+L*(h-hb)"),
            ("pressure_L_nonzero", "p=pb*(T/Tb)**(-g0/(Rair*L))"),
            ("pressure_L_zero", "p=pb*exp(-g0*(h-hb)/(Rair*Tb))"),
            ("density", "rho=p/(Rair*T)"),
        ),
        fixed_boundary_conditions=(
            ("h0", 0.0, "m"),
            ("p0", 101325.0, "Pa"),
            ("T0", 288.15, "K"),
        ),
        conditions=(
            "Fixed sea-level boundary conditions; no caller boundary conditions",
            "No mesh or time conditions; inclusive input bounds for both altitude kinds",
        ),
        sources=(
            ("PDAS atmosphere definition", "https://www.pdas.com/atmosdef.html"),
            (
                "PDAS hydrostatic equations and altitude conversion",
                "https://www.pdas.com/hydro.pdf",
            ),
        ),
        status="metadata_only",
        test_evidence="NOT_ESTABLISHED",
        solver_qualification="NOT_ESTABLISHED",
        physical_validation="NOT_ESTABLISHED",
        execution_authorized=False,
        limitations=(
            "Standard dry reference; no weather or humidity",
            "No pressure-altitude inversion",
            "No extrapolation or aircraft-feasibility assessment",
            "Pin identifies bytes only",
            "Metadata is not a trusted executable general registry or M1 completion",
            "Repository-owned single model; no caller registration or promotions",
        ),
    ),
)


def atmosphere_catalog() -> tuple[AtmosphereMetadata, ...]:
    return _CATALOG
