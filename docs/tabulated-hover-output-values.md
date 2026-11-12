# Tabulated hover output values - V105 prerequisite

The private `_validate_output_values(values, request)` in
`physimesh.drone.tabulated_hover_bemt_request` checks an actual V103 JSON output
slice. It returns `None` on acceptance and raises on failure. It does not copy
or mutate either argument, export a dataclass, solve for inflow, or call a model.
This extraction supports later separately reviewed reference-air composition.
It adds no public API or workflow integration.

`values` must be an exact builtin dictionary with exactly the `_OUTPUT_UNITS`
keys. Arrays and stations must be builtin lists. Stations must be exact builtin
dictionaries with radius, chord and blade angle keys. Physical output numbers
must be builtin floats, finite and normal or explicitly permitted zero. Boolean
and integer substitutes fail even when equal to a float. Counts must be builtin
integers. Metadata must match the request and keep the existing nonblank, UTF-8,
length and geometry-kind rules.

The existing output JSON budget applies independently: root depth 1, depth at
most 10, 32768 nodes including keys, 2048 items per container, 2000 characters
per string, and 1023 bits per integer. Stations remain bounded to 2..256 and
annuli to 1..2048. Cycles fail the depth bound. Aliases count at every occurrence
and must independently satisfy field shape and arithmetic checks, as they would
when repeated in JSON. Container identity provides no shortcut through a budget
or validation check.

The request must be a builtin dictionary containing the twelve core fields used
by the existing validation. This is slice validation, not whole-request admission:
`evaluation` and unrelated fields are not inspected. No request defaults or dummy
density are supplied. Radius, cutout, counts, stations and source declarations
bind directly to the request. Density, angular speed, blade count, lift slope and
drag bind through the existing governing arithmetic and SI normalization.

A single governing path checks geometry coverage and ordering, exact midpoint
locations, piecewise linear interpolation, solidity, zero and nonzero inflow,
angles, local blade/momentum balance, integrated coefficients, summaries, thrust,
power and torque. Operation order is retained. The unchanged local balance guard
is `abs(blade - momentum) <= (64 * sys.float_info.epsilon) * S`, where `S` uses
the largest absolute blade operand before cancellation or momentum term. Coherent
changes to inflow and all dependent summaries still fail this guard.

`_validate_solution` retains the actual exact `TabulatedHoverSolution` type,
frozen declaration, exact dataclass and instance fields, markers, builtin float
members, tuple arrays and actual exact frozen `GeometryStation` fields before
export. `_export_solution` copies only the actual typed result. The wrapper then
validates those actual JSON values with the helper and returns them for the
existing response. No substitute dataclass or marker envelope is constructed.

A future composition must separately validate the actual whole response,
status, markers, output units, request snapshot and request/evaluation hashes.
Passing this helper does not establish any of those envelope or provenance facts.
The existing evaluator keeps that responsibility and its atomic failure behavior.
These safety checks establish no physical, numerical or runtime qualification.
