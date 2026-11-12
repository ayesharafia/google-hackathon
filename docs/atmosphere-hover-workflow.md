# Atmosphere and isolated-hover workflow

`evaluate_atmosphere_hover` composes the two accepted components,
`standard_atmosphere` and `evaluate_hover_bemt`, for an experimental isolated-hover
calculation.

The request has exactly three top-level keys:

- `evaluation`: `standard_atmosphere_isolated_hover_experimental`.
- `atmosphere`: exactly `altitude_m` and `altitude_kind`. The altitude is a finite
  numeric value (not a boolean), from 0 through 30000 metres; `altitude_kind` is
  exactly `geometric` or `geopotential`.
- `rotor`: the hover component's exact rotor request schema with
  `density_kg_m3` omitted. Caller-supplied density is forbidden, even when it is
  valid. Extra rotor keys are rejected; the hover component validates the rotor
  values.

Input JSON is bounded to 512 nodes, depth 8, and strings of at most 2000
characters. Hover outputs are bounded to 20000 nodes, and the annuli limit is
2048.

The atmosphere density supplies the hover request's `density_kg_m3`. This is a
scalar transfer in kg/m^3; it is not a conservation proof. Successful stages retain
copied input and result records with SHA-256 hashes. These hashes describe the
records, not immutability, runtime code identity, or physical validation.

If hover fails after the atmosphere completes, the completed atmosphere stage can
remain in `stages`, while final `outputs` is empty. A completed atmosphere stage
does not imply a completed workflow.

The standard atmosphere is a reference atmosphere, not local weather. The BEMT
component uses a small-angle model whose physical applicability is not
established. It includes no loss factors, swirl, stall, compressibility, or
rotor/aircraft interference. Reported shaft power is not electrical input power.

Nominal results retain `physical_validation` and `numerical_qualification` as
`NOT_ESTABLISHED`, `evidence_level` as `unverified`, and `aircraft_status` and
`feasibility` as null. This workflow establishes neither feasibility nor physical
validation. It is not a general DAG engine or evidence that M3 is complete. It
does not add an API, runtime jobs, network access, or filesystem operations.
