# Next safe task: fixed-pack energy provenance

Kind: documentation. Zone: green. Proposed from SLICE-001's imported-value gap,
not a new battery model or scientific acceptance campaign.

User: an aircraft designer who needs to know why a payload calculation reports
one available energy budget and whether reserve was counted once.

Scope: trace screening_scope.pack_consistency and its direct mass/energy inputs;
read the related schema, retained fixed-pack contract and fixture definitions.
Document the kg * Wh/kg * usable_fraction * (1-reserve_fraction) * 3600 J/Wh
calculation, units, mass selection, consistency guard and missing provenance.
Link source locations and distinguish exact conversion, declared data, model
assumptions and numerical policy. A source label is not authenticated approval.

Acceptance: produce docs/validation/fixed-pack-energy-provenance.md with all
direct formula inputs/guards accounted for, exact source/hash references and
explicit missing evidence. Confirm source bytes and approved thresholds remain
unchanged with bounded static checks. Do not execute model/test campaigns unless
the user requests them. No battery sizing, SOC/sag/thermal implementation,
tolerance changes, new dependencies, dataset import or flight claims.

Rollback: remove only the new document and its task evidence. Preserve all
existing source, records, results and branches. DR-01 and real-aircraft approval
remain pending; this task does not need those decisions to document current code.
