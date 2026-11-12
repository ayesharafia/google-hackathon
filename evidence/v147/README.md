# V147 stable-vs-legacy polar-rotor benchmark evidence (company-scoped, immutable)

Declared family question CLOSED (reviewer-accepted 2026-11-12): equivalence only; no
robustness improvement demonstrated. No production integration. No physical,
validation, aircraft or superiority claims.

- spec-v1.txt / spec-v2.txt: pre-execution specs (sha256 8574bd47..., 3468b73a...)
- Harnesses: tests/drone/stable_polar_rotor_benchmark_v147_v1.py (sha256 17681e9f...),
  tests/drone/stable_polar_rotor_benchmark_v147_v2.py (sha256 83c27ea5...)
- r0-consumed/: v1 R0, consumed and accepted as bounded evidence (manifest sha256
  d1381b26...). 24/24 admission parity; 6 benign paired cases bit-identical; 18
  unsigned refusals by solver design (V135-inherited branch condition).
- v2-attempt1-interrupted/: v2 attempt 1, consumed by an external launcher
  interruption (agent error, not harness/numerical). 7 cases complete, retained
  verbatim; see v2-attempt2-replacement/ATTEMPT-LEDGER.txt.
- v2-attempt2-replacement/: the valid v2 replacement attempt (authorized replacement,
  same pinned harness hash). COMPLETE, 24/24 admitted both solvers, 48/48
  SEALED_VERIFIED, 62/90 annuli converged + 28 NOT_BRACKETED with identical
  per-annulus states/work both solvers, 16 paired-total cases all deltas exactly
  0.0, 8 cases no paired totals. manifest.json sha256 56afc4a9...

Label: numerical difference between two unvalidated solvers on identical synthetic
inputs; not an error estimate, not physical accuracy, not a validation result.
