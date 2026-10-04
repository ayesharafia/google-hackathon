# Local mission capacity contract

The first local implementation uses `local_mission_capacity_v2`, validated by `drone/local_results.py`. This is a separate local draft-study contract. Existing approved-package `AircraftStudyV1`/`AircraftStudyV2` and sphere `ResultsV1` remain unchanged. A general approved aircraft V3 remains pending under IP10; local consistency validation cannot provide authenticated engineering approval.

Every new study binds its frozen project revision, canonical snapshot hash, retained performance-source byte hashes, model source fingerprint and NumPy/SciPy versions. The canonical result bytes are retained as an artifact. Export returns those same bytes. Repeated submission retains one winning result association; old revisions and studies survive draft edits and restart.

For required alternatives, the headline is the minimum individual bound only after every required case passes again at that same payload. Zero payload is not assumed feasible. There is no bisection or extrapolation across a missing feasible interval.

For a chronological mission, the typed successor supports a lower aggregate bound without inventing a limiting case: `aggregate_limit=sequence_energy`, `limiting_case_id=null`. Each segment names an eligible case, explicit duration, source note and `power_profile=constant`. The joint bounded allocation enforces required cases and the one-pack aggregate energy budget. It independently recomputes all cases at the resulting common payload and retains a segment energy ledger. Missing evidence, differing common payloads, residual failures, altered segment powers or inconsistent energy sums refuse contract validation.

`feasible` identifies a numerically checked point inside the declared restricted model. `infeasible` needs a checked bounded linear-combination certificate. Solver failure, time limit or a failed recomputation is `unresolved`. Missing or uncovered physics/data is `unsupported`. None establishes installed-aircraft validation or an operational payload allowance. All local records have `engineering_approval=pending`.

Retained local V1 bytes remain readable and are never migrated in place. V2 adds chronological energy. An older model fingerprint remains associated with the old study; rerunning changed code creates another specification hash. The fingerprint is a local source/library identity, not an immutable deployment attestation.

The initial profile excludes variable-power trajectories, nonzero inflow, maneuvers, thermal/sag state and battery resizing. Constant-power integration is exact (`P*duration`); it needs no numerical quadrature. Variable-power quadrature and independently reviewed uncertainty scenarios remain separate IP11/IP12 extensions.
