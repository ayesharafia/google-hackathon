# Next slice: constants and guard provenance inventory

Kind: documentation. Zone: green preparation. Not a physics implementation.

User value: make the assumptions and numerical policies behind a payload result
inspectable before changing formulas or claiming greater accuracy.

Scope: inspect existing atmosphere.py, performance.py, trim.py, capacity.py and
mission_capacity.py. Produce docs/validation/drone-constants-ledger.md, linking
each discovered physical constant/guard to source location, units and citation
or explicit UNVERIFIED status. Classify definitions and historical software
policies separately from physical uncertainty. Explain excluded literals.

Acceptance: cover all 5 modules, classify 100% of discovered relevant constants
and guards, invent 0 citations/values and change 0 model values or tolerances.
Use a bounded source/link/hash check when verification is authorized; report
unavailable evidence. No migration of constants or new dependency is included.

Rollback: remove only the new inventory document if rejected; preserve source,
approved tolerances, results and all pre-existing user work.

Dependencies: actual source audit complete. Qualified review and real aircraft
acceptance remain separate. The inventory confers no physical validation.
