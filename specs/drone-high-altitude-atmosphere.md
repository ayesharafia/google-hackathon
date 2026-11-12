# Physics Spec: Layered 20-30 km standard atmosphere (U.S. Standard Atmosphere 1976)

Status: DRAFT FOR IMPLEMENTATION v2 (internal implementation prep; candidate review before publication)
Domain: drone
Author: Instinct task agent (spec-writer)   Reviewer: independent engineering review (spec ACCEPTED
subject to the corrections applied in this v2)   Date: 2026-11-12
Increment: V152 candidate

v2 changes (independent reviewer corrections applied):
- REQUIRED 1: transcription caveat extended to the table-2 R*/r0/sigma misprints (S note
  already present in v1), per the errata sheet appended to the NOAA scan.
- REQUIRED 2: 0-11 km no-regression check tolerance pinned at 1 x 10^-4 relative, because
  the existing `isa_troposphere` uses R_air = 287.05 J/(kg*K) while USSA-1976 implies
  R*/M0 = 287.0529 J/(kg*K) (~1e-5 relative difference in the pressure exponent).
- NARRATIVE 1: cross-check self-report corrected to the actual recomputed pressure
  deviations (+1.6e-5 at 20000 m', +9.3e-6 at 25000 m', +5.7e-5 at 30000 m').
- NARRATIVE 2: M = M0 statement scoped: the source holds M = M0 to about 80 km and
  departs by up to 0.04% across 80-86 km (table 8); exact within this slice's 0-47 km'.
- NARRATIVE 3: page-locator offset corrected: PDF page = document page + 16 in the main
  text, but +15 around document pages 60-63 (an unfilmed blank page shifts the table
  region).

## 1. What this feature does (plain language, 3 lines max)

Extends the drone atmosphere model from today's ISA troposphere (0-11 km only) to the
U.S. Standard Atmosphere 1976 layered definition covering geopotential altitude
0 to 47000 m'.
Above 11 km it uses the standard's own layers (isothermal 11-20 km, +1.0 K/km' 20-32 km,
+2.8 K/km' 32-47 km); it never extrapolates the tropospheric lapse rate past 11 km.
Outside the supported range it refuses with a declared error, as today.

## 2. Why the product needs it

The original PHYSIMESH Drone Module specification (O1, received 2026-11-05 23:11 IST)
requires layered 20-30 km atmosphere fixtures and states the tropospheric lapse rate
must never be extrapolated. Verified at HEAD 13dbf3d1: `isa_troposphere` in
`src/physimesh/drone/atmosphere.py` raises above 11000 m, so the 20-30 km mission
regime the product targets is currently unservable. This is a concrete original-spec
gap (gap map v2, row R5), not a new capability request.

This spec authorizes the layered atmosphere evaluation only. It authorizes no mission,
rotor, battery, coupling, UI, or API contract change beyond what is needed to expose
the extended range through the existing atmosphere functions; any consumer behavior
change stays in its own scope. Physical validation is not claimed: the fixtures below
are reproducibility checks against the published standard, not measurements.

## 3. Primary source and rights

- U.S. Standard Atmosphere, 1976. NOAA-S/T 76-1562; U.S. Government Printing Office,
  Washington, D.C., October 1976. COESA (NOAA, NASA, USAF).
- Copy used: NOAA online publication PDF
  https://www.ngdc.noaa.gov/stp/space-weather/online-publications/miscellaneous/us-standard-atmosphere-1976/us-standard-atmosphere_st76-1562_noaa.pdf
  (18,267,064 bytes, fetched 2026-11-12; internal reference only, not committed).
  The scan carries no OCR text layer and ends with an appended third-party errata
  sheet (Yekta Gursel via NASA STI); the errata concurs with each table misprint
  disclosed below.
- Rights: U.S. Government work; constants, equations and tabulated values are
  reproduced with citation. No third-party redistribution issue identified.
- Applicability notes from the source itself: identical with the ICAO Standard (1964)
  up to 32 km and the ISO Standard (1973) to 50 km (abstract, doc p. v). The standard
  represents idealized mean conditions (foreword).
- Page locators: "doc p. N" is the printed document page. In the NOAA scan,
  PDF page = doc page + 16 through the main text; around doc pp. 60-63 (Table I region)
  the offset is +15 because an unfilmed blank page shifts the sequence.

## 4. Conventions and constants (source-verified)

Altitude conventions (1.2.3, doc pp. 7-8):
- Geopotential altitude H (geopotential meters, m') is the table argument.
  H = (g0/g0') * (r0 * Z / (r0 + Z))   [eq 18];  Z = r0 * H / (r0 - H)   [eq 19],
  with Gamma = g0/g0' = 1 m'/m exactly. Geometric altitude Z in meters.
- g0 = g0' = 9.80665 m/s^2 (Category II, table 2B; g0' = 9.80665 m^2/(s^2*m')).
- r0 = 6,356,766 m (doc p. 8 text: "the value of r0 is taken as 6,356,766 m").
- API must declare whether input altitude is geometric or geopotential and convert
  with eqs 18/19; no silent mixing.

Constants (tables 2A/2B and text, doc pp. 2-3, 9, 19):
- R* = 8.31432 x 10^3 N*m/(kmol*K);  k = 1.380622 x 10^-23 N*m/K;
  N_A = 6.022169 x 10^26 kmol^-1.
- M0 = 28.9644 kg/kmol (doc p. 9 text).
- P0 = 1.013250 x 10^5 Pa;  T0 = 288.15 K.
- gamma = 1.40 (exact, dimensionless).
- Sutherland: beta = 1.458 x 10^-6 kg/(s*m*K^(1/2)); S = 110.4 K
  (doc p. 19 text governs).
- sigma = 3.65 x 10^-10 m (not needed for this slice; recorded for completeness).

TABLE-2 MISPRINT DISCLOSURE (all four verified against the rendered scan and the
appended errata sheet; the values above are the correct ones and appear in the
standard's own text pages):
- Table 2A prints R* = 8.31432 x 10^-3 N*m/(kmol*K) - a factor-1e6 misprint; the
  correct 8.31432 x 10^3 appears in the doc p. 3 text.
- Table 2B prints r0 = 6.356766 x 10^6 km - a factor-1000 unit misprint; the doc p. 8
  text gives 6,356,766 m.
- Table 2B prints sigma = 3.65 x 10^-1 m - a factor-1e9 misprint; correct is
  3.65 x 10^-10 m.
- Table 2B prints S = 110 K; doc p. 19 text says 110.4 K, which this spec pins.

Layers (table 4, doc p. 3 - geopotential base heights and molecular-scale
temperature gradients; scope of this slice is layers b = 0..3):

| b | H_b (m') | L_M,b (K/m')     |
|---|----------|------------------|
| 0 | 0        | -6.5 x 10^-3     |
| 1 | 11000    |  0.0             |
| 2 | 20000    | +1.0 x 10^-3     |
| 3 | 32000    | +2.8 x 10^-3     |

Upper boundary of this slice: H = 47000 m' (top of layer 3). H < 0 or H > 47000 m'
is refused. (The standard continues to 84.852 km'; extending past 47 km' is a future
spec, not this one.)

## 5. Governing equations (source-verified)

Within this slice (0-47000 m'), M = M0 and kinetic temperature T = T_M. (Source scope
note, 1.2.4 doc p. 9: M = M0 holds to about 80 km and departs by up to 0.04% across
80-86 km per table 8; exact within this slice, and any future extension past 47 km'
must carry the M variation explicitly.)

Molecular-scale temperature, piecewise linear per layer b:
  T_M(H) = T_M,b + L_M,b * (H - H_b),  T_M,0 = T0.
Plain English: temperature walks each layer at that layer's fixed gradient, starting
from 288.15 K at sea level; it is continuous across layer boundaries.

Pressure (1.3.1, doc p. 12):
  L_M,b != 0:  P = P_b * [T_M,b / (T_M,b + L_M,b*(H - H_b))]^(g0'*M0/(R*L_M,b))  [eq 33a]
  L_M,b == 0:  P = P_b * exp[-g0'*M0*(H - H_b)/(R*T_M,b)]                        [eq 33b]
  P_b for b >= 1 is obtained by applying the appropriate equation at H = H_{b+1}
  (i.e., pressure is continuous across boundaries, computed by walking layers from
  P0 at H = 0).
Plain English: hydrostatic balance integrated over each linear-temperature layer.

Mass density (1.2.2 eq 1, doc p. 6, with M = M0):
  rho = P * M0 / (R* * T).
Speed of sound (1.3.10, eq 50, doc p. 18):
  C_s = (gamma * R* * T_M / M0)^(1/2).   (Small-perturbation limit; the source notes
  attenuation limits at high altitude - applicability caveat to carry in docs.)
Dynamic viscosity (1.3.11, eq 51, doc p. 19):
  mu = beta * T^(3/2) / (T + S).   (Empirical; the source warns of measurement caution
  for 32-86 km - carry as a documented caveat, still within the standard's tables.)

Derived quantities must be labeled derived from USSA-1976, not measured.

## 6. Existing-code integration boundaries

- `isa_troposphere(altitude_m)` keeps its current contract (0..11000 m, raises outside).
- New capability: a layered standard-atmosphere evaluation (e.g.,
  `ussa1976_state(geopotential_altitude_m)` returning pressure, temperature, density,
  and optionally speed of sound and dynamic viscosity) covering 0..47000 m', refusing
  outside with a declared error. Naming follows repo conventions; the exact function
  surface is the implementer's, but the refusal behavior and units are contractual.
- `check_altitude_pressure_consistency` currently embeds the troposphere-only ISA and
  must not silently accept altitudes above 11 km against tropospheric values. It must
  either use the layered model for its ISA comparison or keep refusing above 11 km
  with the same explicit error. No extrapolation either way.
- No change to mission/rotor/battery callers in this slice beyond what compiling the
  new function requires. Existing tests must keep passing unchanged.

## 7. Acceptance fixtures (published Table I values, transcribed from the primary scan)

Geopotential-altitude Table I rows (20000/25000: doc p. 60; 30000: doc p. 62;
reviewer pixel-verified at 300 dpi):

| H (m') | T (K)  | P (mb)   | rho (kg/m^3)     |
|--------|--------|----------|------------------|
| 20000  | 216.650 | 54.748  | 8.8035 x 10^-2   |
| 25000  | 221.650 | 25.110  | 3.9446 x 10^-2   |
| 30000  | 226.650 | 11.718  | 1.8012 x 10^-2   |

25000 m' rho discrepancy - explicit adjudication, not silently toleranced: the
published table rounds each column independently, and at 25000 m' its rho column
(3.9446 x 10^-2) is the outlier against the table's own P and T columns and its own
rho/rho0 column (3.2217 x 10^-2 x 1.2250 = 3.9466 x 10^-2). An independent
from-equations layer walk with exact constants gives rho = 3.94658 x 10^-2 there,
matching the rho/rho0 column to ~2e-6 and differing from the rounded rho column by
5.0 x 10^-4 relative. Acceptance tolerances: T exact to 0.001 K; P relative 1 x 10^-4;
rho relative 1 x 10^-3 against the published values above.

Required checks:
- The three fixtures above within tolerance.
- Layer-walk continuity: T and P continuous at 11000 / 20000 / 32000 m'.
- Refusal at H = -1 m' and H = 47001 m'.
- No-regression agreement of the 0-11 km branch with existing `isa_troposphere`
  outputs within 1 x 10^-4 relative on pressure (pinned tolerance; exact agreement is
  impossible because `isa_troposphere` uses R_air = 287.05 J/(kg*K) while USSA-1976
  implies R*/M0 = 287.0529 J/(kg*K), a ~1e-5 relative difference in the pressure
  exponent; the 1e-4 pin covers it with margin).

Independent cross-check performed while drafting (this agent's fresh from-equations
implementation, 2026-11-12): T matches the print exactly at all three fixture
altitudes; recomputed pressure deviates from the published values by +1.6 x 10^-5
(20000 m'), +9.3 x 10^-6 (25000 m'), and +5.7 x 10^-5 (30000 m') relative - all within
the 1e-4 fixture tolerance (reviewer's independent recompute concurs with these
deviations).

## 8. Explicit non-goals and non-claims

- No altitudes above 47000 m' (future spec), no winds, no variability/perturbations
  (the standard's Part 2 systematic variations are out of scope).
- No physical validation, no mission-capability claim, no 750 kg / 20 km feasibility
  claim. This is standard-atmosphere reproducibility only.
- No UI work. No API contract change beyond the additive function surface.
- No reuse of the UIUC PDB or LSAT data in this slice.
