# ADR-0002: Calculate payload capacity for the supplied design

Date: 2026-10-02. Status: accepted from the customer's explicit correction.

The initial source manifest set 750 kg of carried payload as a requirement.
The customer replaced that goal: the product must report how much payload an
approved design can lift. No fixed payload target remains. The source manifest
and reference tests are retained as historical evidence; the customer decision
governs new product behavior.

`mission.payload_mass_kg` is optional **installed** payload in an operating
case, with no default. If supplied, it must equal the mass ledger's payload
category. Empty-aircraft mass is the complete mass ledger's total less its
installed payload. The mass ledger still needs an explicit payload category,
which can contain a 0 kg item. No mass is inferred from STL volume.

For each declared mission case, a screening calculation will use traceable
rotor performance at stated operating and motor limits, body download,
environment, attitude and vertical acceleration. It will report a payload
capacity or an explicit reason it cannot calculate one. The summary capacity
is the lowest across **all required supplied cases**. Missing data never
silently removes a case. Motor power, energy and reserve gates must pass before
the result is shown as an operable mission capacity. The result remains
`screening_only` until the numerical and experimental evidence gates in the
master plan are met.

The three-day demonstration uses an illustrative multirotor project with each
value marked as example input. No capacity for the customer's aircraft is
reported until its geometry, rotor data, mass ledger and mission cases arrive.

The existing `drone_manifest_v1` schema is a draft without client data. Its
payload field changes in place to optional installed payload under this
customer revision. Before importing any previously stored external v1 project,
we must add an explicit migration that asks whether its payload value was an
installed mass or the former target.
