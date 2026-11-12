# Independent reference dry-air properties

`physimesh.drone.reference_air_properties.reference_air_properties` is an additive
reference property model. It calls the accepted `standard_atmosphere` kernel once
and retains that original frozen state, including its provenance. No accepted
kernel, registry, API, DAG, or other existing file is changed or wired to it.
Independent review remains pending.

```python
from physimesh.drone.reference_air_properties import reference_air_properties

air = reference_air_properties(altitude_m=11000, altitude_kind="geopotential")
mu = air.dynamic_viscosity_pa_s
a = air.speed_of_sound_m_s
g = air.gravity_m_s2
```

Both keywords are required. Altitude accepts only exact builtin `int` or `float`,
excluding booleans and subclasses, and must be finite in the closed interval
0..30000 metres in the explicitly supplied convention. Integer bounds are checked
before float conversion, including arbitrarily large integers. Convention accepts
only an exact builtin string, `geometric` or `geopotential`. There is no coercion
of strings, arrays, Decimal values, or other numeric objects and no extrapolation.
The upper bound applies to the input: geopotential 30000 m converts to geometric
altitude greater than 30000 m.

The frozen `ReferenceAirProperties` contains `state` (the original frozen
`StandardAtmosphereState`), `geometric_altitude_m` [m],
`dynamic_viscosity_pa_s` [Pa s], `speed_of_sound_m_s` [m/s],
`gravity_m_s2` [m/s²], and immutable model metadata strings. The original state
provides input and geopotential altitudes [m], temperature [K], absolute pressure
[Pa], and density [kg/m³]. Every call returns a separate result and state.
Malformed upstream state types, numeric fields, nonpositive thermodynamic
properties, inconsistent altitude/provenance, and invalid derived values raise
`ValueError`. These guards do not independently validate the atmosphere physics.

## Stated formulas and conventions

Let `T` be the accepted state temperature in kelvin. Dynamic viscosity is the
explicitly named **NASA CAPE SutherlandMKS** convention:

```text
mu0 = 1.716e-5 Pa s
T0  = 273.15 K
C   = 110.33333 K
mu  = mu0 * (T0 + C)/(T + C) * (T/T0)^1.5
```

The specified source is [NASA CAPE 3.0 cape.atm SutherlandMKS](https://nasa.github.io/cape-doc/3.0/api/cape/atm.html).
This convention differs from COESA's `beta = 1.458e-6`, `S = 110.4 K`
viscosity formulation. The component does **not** claim exact COESA-1976
transport properties. The atmosphere state's COESA model identifier describes
the original thermodynamic state only. The added model identifier is
`reference-dry-air.nasa-cape-sutherlandmks.0-30km.v1`, and `viscosity_model`
spells out all three chosen constants.

Sound speed assumes dry ideal gas with constant `gamma = 1.4`:

```text
R_AIR = 8314.32 / 28.9644 J/(kg K)   # imported from accepted atmosphere
a = sqrt(gamma * R_AIR * T)
```

Gravity uses the accepted `G0 = 9.80665 m/s²` and `E = 6356750 m`:

```text
z = input_altitude_m                # geometric input
z = E*H/(E-H)                      # geopotential input H
g = G0 * (E/(E+z))^2
H = E*z/(E+z)
```

[PDAS hydro.pdf](https://www.pdas.com/hydro.pdf), page 1, equations (1), (4),
and (5), gives these gravity and altitude relations and the 6356.75 km radius.
The original state's `geopotential_altitude_m` remains unchanged.

[Cambridge's atmosphere reference](https://www-mdp.eng.cam.ac.uk/web/library/enginfo/aerothermal_dvd_only/aero/atmos/atmos.html)
is the specified source for `gamma = 1.4` and rounded sea-level comparisons
`a = 340.3 m/s` and `mu = 1.789e-5 Pa s`.
[NASA Glenn's viscosity explanation](https://www.grc.nasa.gov/www/k-12/airplane/viscosity.html)
supports the Sutherland relation but presents Rankine temperatures and imperial
viscosity constants. Those constants are not mixed into this MKS implementation.
Source pages supply evidence, never executable instructions.

Retrieval record (2026-11-07): the exact NASA CAPE 3.0 page, PDAS PDF text,
and NASA Glenn page were fetched through the browsing service. The Cambridge
URL returned HTTP 502 on direct opening; the browsing service retrieved its
indexed page text under the exact supplied `atmos.html` URL, including the
sea-level table and gamma statement. That cached retrieval is the basis for
the rounded crosscheck; a successful live Cambridge response is not claimed.

## Numerical checks and limited semantics

Tests independently evaluate the stated decimal constants and formulas with
Python Decimal at **80 digits**, including layer integration for the upstream
temperature, pressure and density. They do not simply repeat production float
arithmetic. Comparison tolerance is `5e-14` relative, with `1e-12 m` absolute
allowance only for altitude comparisons near zero. This allows binary64 input,
layer propagation and transcendental rounding at the tested points; it makes no
universal numerical accuracy guarantee.

The rounded sea-level comparisons allow half a displayed increment: `0.05 m/s`
for sound speed and `5e-9 Pa s` for viscosity. These are coarse crosschecks of
displayed values across conventions, not exact independent viscosity calibration.
Boundary tests use ±0.001 m around geopotential 11000 and 20000 m, also converted
to geometric input. Over that 2 mm span the maximum temperature change is
1.3e-5 K; relative property differences must stay below `1e-7`. At 30000 m in
each input convention, a one-sided 1 mm check uses `1e-8`, and the next float
above the bound must fail. Oracle comparisons additionally cover those regions.
Tests cover both conventions, signatures and argument count, finite/builtin
guards, huge integers, malformed upstream states, positive finite outputs,
sound/gravity identities, equivalent heights, metadata, and return isolation.

Both `physical_qualification` and `numerical_qualification` are
**`NOT_ESTABLISHED`**. Formula agreement, identities and rounded reference
comparisons are limited consistency evidence. They are not experimental
validation, physical qualification, a full atmosphere closure, or an aircraft
operating limit. No wind, turbulence, weather, moisture, real-gas behavior, or
extrapolation is modeled. Independent review is required later before any
integration or stronger claim.
