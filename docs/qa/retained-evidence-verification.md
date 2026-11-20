# Independent retained evidence and historical source checks

I03 provides `scripts/verify_evidence.py` with three explicit scopes:

```sh
.venv/bin/python scripts/verify_evidence.py evidence --native --vendor
.venv/bin/python scripts/verify_evidence.py source-commit
.venv/bin/python scripts/verify_evidence.py both --native --vendor
```

Evidence scope verifies the frozen inventory's documentary records, complete result-package membership, manifest and every member's size/hash, provenance bindings and supporting files. Optional native scope checks the ordered coarse/medium/fine records, exact input hashes and output bytes. Optional vendor scope checks the retained archive. Unrequested scopes remain explicitly unchecked. `--data-root` can select an exact relocated data copy; native files and documents remain relative to the repository.

Source scope resolves the inventory's full 40-character Git commit, reads each named regular Git blob and checks its size/SHA-256. Symlinks, submodules, absent commits/paths, incorrect sizes/hashes and files above the bounded 8 MB read are refused. It does not check out the commit, change HEAD/worktree, execute Python from the historical source or run OpenFOAM. Source scope refuses evidence-only options.

The original `postpro/baseline.py`, `scripts/verify_baseline.py` and P00.1 inventory are unchanged. Their current-source verification still refuses changed checkout files. The new evidence scope permits later software checkouts to inspect earlier retained bytes without certifying their current calculations. Both implementations use the frozen inventory protocol; any future baseline protocol requires an explicit versioned change.

Performed 5 October 2026: `both --native --vendor` verified 130 historical source files at `d17f97a6d37d4458e08f005a20ecf5db870b3235`, four documentary records, 33 package members, 31 supporting files, 105 retained native outputs and the vendor archive. The package is `acd1b8716144aeaa`; the complete result is recorded in `retained-evidence-verification.json`.

These are byte-identity checks. `solver_rerun=false`, current source is unchecked, evidence remains `unverified`, machine review remains `pending`, aircraft validation remains `not_established` and human release approval remains `pending`. The retained Claude review is checked as documentary bytes, not a newly performed physics review. No cause is assigned to the retained correlation discrepancy.

Tests exercise changed current source, unchanged original-checker refusal, document/support/package/native/vendor corruption, unexpected members, escaping symlinks, relocation, unchecked scopes, exact historical Git reads, missing commits/paths, wrong hashes, non-regular Git objects, CLI selection/refusal and unchanged checkout state. Tests do not execute a solver.

Exact historical-source execution and numerical reproduction remain pending. The source-commit command only completes the byte-inspection part of I03. A fresh isolated environment, pinned dependencies/backend, bounded execution budget and retained comparison receipt are required for a reproduction claim.
