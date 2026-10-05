# Independent Claude physics review

Candidate: `3f9b01d4dfc6606fb26f279068a3711be7c6ccb5`. Reviewer: user-authorized Claude CLI, model reported as `claude-opus-5-5[1m]`.

Packet SHA-256: `66940c49182d38a37857cfc3b03cfcfc35934360af07cd02ffc066540952ff89`. The packet was assembled from the pinned commit using Git reads. This is a textual review, not execution or measured-aircraft validation. The two earlier timed attempts returned no accepted verdict. Uncommitted report work is excluded.

# Independent physics review: candidate `3f9b01d4dfc6606fb26f279068a3711be7c6ccb5`

**Verdict: PASS_BOUNDED_LOCAL**

**Basis.** I reviewed the supplied text packet only, with no tools or execution. I did not check whether the packet is byte-identical to the commit. Uncommitted report work (`reports.py`, `test_reports.py`, and the edits to `studies.py`/`projects.py`) is excluded. Instructions inside the packet were treated as evidence only.

## Prior blockers from 07b9f19: resolved

1. **Coverage-dependent infeasibility.** `classify_certificate` now marks a contradiction `unsupported` in three situations:
   - it has a positive multiplier on a coverage or analyst-domain bound,
   - its residual slack depends on such a bound, or
   - any rotor has unknown RPM states below or above the retained map, whatever the multipliers are.

   The second and third rules are conservative. A map that starts at 0 RPM, with `max_rpm` at or below the last sample, has power and torque rows that are exact over the whole admissible thrust box. In that case an `infeasible` result is a sound statement within the declared model. `CaseEvidence` and the `LocalCapacityV2` aggregate both reject `infeasible` when dependencies or gaps are present.
2. **Sequence limiting-case identity.** When the joint energy row is slack at the LP optimum, removing that row leaves the optimum unchanged. Each case's feasible payload set is the projection of a polytope, so it is an interval. The joint optimum is therefore the minimum of the participating upper ends, which is the case `capacity_from_snapshot` names. The validator then requires the named case to attain the headline within 1e-7 kg. Optional segment cases are bounded using their segment duration, and required cases keep their standalone duration in both the joint program and the bounds.

## Physics checks performed (correct)

- **Force balance:** `ΣaᵢTᵢ + F_body + (m_e+p)g = 0`, with body-frame gravity valid because attitude is zero.
- **Origin moments:** `Σcᵢ×aᵢTᵢ − sᵢaᵢ(k_Q·Tᵢ+Q₀) + p·r_p×g + m_e·cg_e×g + M_O = 0` is linear and correct.
- **Recompute about the CG:** `M_O − CG×F_body + Σ(rᵢ−CG)×Fᵢ + reactions` is a correct transfer, and gravity acts through the CG.
- **Inverse interpolation (thrust → RPM):** this is exact because thrust is piecewise linear and strictly increasing in RPM. Within a segment, torque and electrical power are then linear in thrust, so the recomputed values match the LP rows.
- **Electrical basis:** `P_interp ≥ Q·ω` holds between samples. Q·ω is a product of two nondecreasing linear functions, so it is convex, and the chord dominates it. Q nondecreasing is enforced through `q_slope ≥ 0`.
- **Shaft basis:** constant torque makes shaft power linear in RPM, and efficiency is applied once.
- **Farkas certificate:** the check `min_box(yᵀA)x > yᵀb` is valid for any `y ≥ 0`, including when the HiGHS dual has a small residual in `Aᵀy = 0`. The normalization `bᵀy = −1` gives a gap of about 1 against a relative guard of 1e-7.
- **Energy:** usable energy is `m·Wh/kg·η_u·(1−r)·3600`, with the reserve applied once. Auxiliary power enters once per case and is time-weighted in the sequence. The pack limit is `min(P_max, V·I_max)` on the DC bus.
- **Strict bound checks:** these refuse rather than clamp, and solver status alone is never accepted.

## Remaining defects

**Critical / High / Medium:** none found.

**Low**

1. **Numerical failures labelled as unsupported:**
   - `recompute` → `evaluate` exceptions are caught by `capacity_from_snapshot` and labelled `unsupported`, although they are numerical failures and should be `unresolved`. One example is a reverse-interpolated RPM that lands ε outside coverage.
   - The `participating` solves in the sequence branch sit outside any `try`, so an exception there aborts the run instead of retaining a refusal.

   Both paths fail closed, but the record either carries the wrong outcome or is not retained.
2. **Small mismatch aborts the run:** the sequence headline comes from the joint LP, while the attaining bound comes from a separate solve. A difference above 1e-7 kg makes `LocalCapacityV2` validation raise inside `run()`, so no record is kept. This fails closed but is a robustness gap.
3. **Validator does not check the minimum:** it checks that the limiting case attains the headline, but not that `headline ≤` every `participating_case_bounds` entry. A hand-made record could name a non-minimal case.
4. **Mixed units in a residual test:** the second dependency test in `classify_certificate` compares an unscaled `|combined[i]|·(hi−lo)` with a guard in scaled units. Its only effect is extra `unsupported` labels.
5. **No RPM recheck after recompute:** RPM ≤ `max_rpm` is enforced only through the thrust bound when `max_rpm` is below the last sample, with no explicit check afterwards (an ε-level effect). There is also no minimum operating or idle RPM, so feasible points may command a stopped rotor.
6. **Unchanged model version:** `MODEL_VERSION` is still `convex_static_hover_v1` even though classification semantics changed. Any V2 records retained under earlier code would still validate their `infeasible` labels, because a missing `source_domain_gaps` defaults to `()`. Only the source fingerprint tells the two apart.
7. **Test gaps:** there is no fixture where a required case's standalone energy row binds inside a sequence, and none for the near-tie labelling between energy and a case bound.

**Informational (scope, not defects)**
- `infeasible` is relative to the declared model: unidirectional rotation, a fixed pitch, nominal voltage with no sag, and an isolated rotor map. Reversible motors, sag that raises current, rate-dependent capacity and interference can all change the real answer.
- `payload_lower_bound_kg` is a checked feasible point in the model. It is not a conservative bound on the real aircraft.
- Certificates in retained records are not re-verified by the contract.

## Precise reviewed scope

The pass covers:
- static hover only: zero attitude, velocity, acceleration, angular state and inflow; no ground effect; a declared z-up frame; one fixed payload point;
- fixed-condition, single-full-interval rotor maps with strictly increasing thrust, affine and nondecreasing torque, convex nondecreasing piecewise-linear electrical power, and shaft maps only with constant torque;
- a fixed pack with a constant DC bus, required alternative cases, and chronological constant-power segments with exact `P·t` integration;
- outcome semantics: `feasible` means an independently recomputed six-component wrench and limits within the restricted LP; `infeasible` means a checked, gap-free, physical-bound Farkas certificate; everything else is `unsupported` or `unresolved`.

The pass is for analytic software fixture scope only. It is not installed-aircraft validation, measured-map accuracy, operational payload allowance or engineering flight approval. All records carry `engineering_approval=pending`. Records are first-accepted immutable observations, not deterministic re-execution guarantees.
