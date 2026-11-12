# V141 resource evidence and serialized headroom

Final private candidate, pending independent code/science/resource review and acceptance.
This document accompanies stable-polar-rotor-small-audit.json, stable-polar-rotor-maximum-audit.json,
stable-polar-rotor-headroom.json and the reproducible resource driver
tests/drone/stable_polar_rotor_audit.py. No conditional benchmark/API/UI exposure is authorized by these observations.

Both resource fixtures have eight contiguous radial annuli, positive hub, fixed synthetic Cl4,
chord.01, broad caller polar coverage and explicit32-call budgets. Angle/residual tolerances are
both1e-30. Geometry-only lower endpoints use max(.1deg,2*atan((1-r/R)/(256*r/R))); upper20deg.
Sixteen genuine preparation residual calls check opposite endpoint signs, native actual f-domain,
and retained positive corrections before recording each fixture's canonical digest. They are not
included in the rotor's256 residual attempts. No measured targets, fabricated solves, cached
responses, solver bypass, tolerance change or configured quota override is used.

| Measured case | Actual solve/residual attempts | Admitted whole solves/residuals | Evaluation wall | Peak RSS KiB |
| --- | ---: | ---: | ---: | ---: |
| Small polar | 8/256 | 8/256 | 12.493826562s | 46960 |
| Configured maximum shape, owner run | 8/256 | 7/224 | 342.267537853s | 302884 |

Small output:5068173 bytes,395761 nodes, depth19. Small expanded units alone:635256 bytes/61599 nodes.
Small retained children alone:4417211 bytes/332856 nodes. Process AS1536MiB/CPU600s/wall90s.
The maximum case uses eight tables of256 rows per polar with maximal escaped declaration strings.
Seven admitted whole objects total61813983 bytes/6708401 nodes; all eight returned objects total
70643910 bytes/7666744 nodes. The eighth exceeded67108864 bytes, while cumulative nodes still
fit8388608. Its parent copy/hash/guard-attempt/guard-success counters are all zero. The atomic
4096-byte failure receipt retained7/224 counts and normal failure hashes, with empty outputs/units.
Maximum process AS1536MiB/CPU600s/wall600s. Its wall includes explicit SIGSTOP pauses reported by
the owner; evaluation CPU301.351572966s and total CPU310.039415843s are recorded separately.
RSS includes interpreter/imports and instrumentation. Upstream child allocation/hash already happened.

Earlier attempt history: owner reported a110-second wall ABORT after3/96 attempts, approximately
148356 KiB peak RSS, no completed response. Its report file was overwritten by the successful
configured run. This note preserves that report, without claiming a recovered original artifact.
Pairwise and explicit abort-receipt lint rationale were added to the audit source afterward;
the actual measured product implementation and fixture values were unchanged. No expensive rerun.

## Conservative current-schema envelope, not a RAM proof

The frozen headroom JSON gives an upper envelope for GUARDED SUCCESSFUL responses. It deliberately
overcounts placeholder nodes/bytes and relaxes physical constraints for token-length accounting.
Reproduce its derivation from the exact frozen catalogs and the canonical encoder as follows:

1. Reserve67108864 bytes/8388608 nodes for the sum of WHOLE actual solve result objects. Every
   result has passed the raw quota, snapshot/exact comparison and independent full solve replay.
2. Reserve the entire8388608-byte/262144-node root input for all returned requests' unchanged
   polar and solve subtrees. Each annulus contributes each such subtree to one returned actual
   request. Counting the whole root input also includes unrelated fields, so this overcounts.
3. Count eight projected actual solve requests with polar and solve replaced by null. Preserve
   exact evaluation/policy/template keys; replace every section numeric value with (2**1023)-1.
   This308-digit positive integer exceeds the serialized lengths of admitted positive native
   numeric inputs and computed floats. This also overcounts chord/pitch already covered by input.
   Canonical total:29032 bytes/392 nodes for the eight request wrappers/repeated global properties.
4. Expand the actual frozen solve output-unit schema to32 residual-unit rows, with full computed
   residual/load/lookup units and present bracket/solution unit dictionaries, and repeat for all
   eight parent annuli. Include full actual-request units, contribution and integrated units.
   Computed unit dictionaries exceed their OOD/null alternatives; every label is frozen and exact.
   This maximum expanded parent units tree is635866 bytes/61685 nodes, depth16.
5. Count the parent receipt/row skeleton separately with actual solve requests/results null,
   output_units empty, eight indexed geometry rows, contributions and integrated totals present,
   and both hashes64 characters. Use the same308-digit integer for all geometry scalars; signed
   contribution/total floats use -sys.float_info.max (maximal finite-float token length24).
   Keep the longer NOT_RUN_SECTION_NOT_CONVERGED rotor label, although totals are present in
   this deliberately relaxed accounting skeleton. Frozen metadata/limits/limitations are included.
   Skeleton total:16047 bytes/345 nodes. Placeholder nulls remain counted when adding subtrees.

Thus bytes <=67108864+8388608+29032+635866+16047 =76178417 <134217728.
Nodes <=8388608+262144+392+61685+345 =8713174 <16777216.
Unused serialized headroom:58039311 bytes; unused node headroom:8064042 nodes.
The child root is embedded at depth5, so accepted child depth36 becomes at most40. Returned
request depth18 becomes at most22; expanded unit depth16 and wrapper depth6 fit40.
These bounds depend on the current exact guarded schemas/labels/native scalar constraints, not
arbitrary unguarded child contents or caller-selectable metadata. Any schema extension needs review.
Final export still independently stream-checks its whole byte/node/depth ceilings before hashing
and after sealing, and refuses on violation. Failure receipts have no retained payload.

The envelope concerns canonical bytes/nodes/depth ONLY. It does not bound object overhead, aliasing,
temporary canonical hash strings/bytes, simultaneous raw+snapshot child allocations, CPU, concurrent
calls or API readiness. Upstream allocation is outside parent quota prevention. Numeric payloads
in the measured maximum-shape fixture were not maximized. No physical qualification follows.

## Verification and exact new files

Owner-observed new tests:48 passed in13.55s. Combined new and accepted section/rotor suites:
518 passed before audit-only lint edits. Ruff passes the three new Python files. No broad regression
or expensive resource rerun was performed merely for audit-only lint/source comments.
Direct comparison against accepted V140 found all661 original src/tests/docs/web files byte-identical
(249/263/99/50). Earlier611 accounting excluded web; it is not the complete final comparison.

Exact new candidate files:

- src/physimesh/drone/stable_polar_rotor.py
- tests/drone/test_stable_polar_rotor.py
- tests/drone/stable_polar_rotor_audit.py
- docs/stable-polar-rotor.md
- docs/stable-polar-rotor-resource-audit.md
- docs/stable-polar-rotor-headroom.json
- docs/stable-polar-rotor-small-audit.json
- docs/stable-polar-rotor-maximum-audit.json

The two actual audit JSON files are evidence receipts, not implementation/physical acceptance.
