# Offline Codex review bundles

This importer makes a manually collected proposal easier to inspect. It does not
run Codex, apply edits, run checks, reserve an attempt, or finish a task. The
provider launcher remains blocked until its isolation boundary is verified.

Use the existing `codex_proposal_inputs.snapshot_inputs` to prepare a source
snapshot from explicitly approved paths and exact hashes. Obtain a proposal
through a separately approved manual process. Save both as UTF-8 JSON, then run
from the repository root:

```sh
python -m scripts.qa.codex_review_bundle \
  --snapshot /absolute/path/snapshot.json \
  --proposal /absolute/path/proposal.json \
  --output-dir /absolute/path/new-review-bundle
```

The output parent must exist, without symlink components. The output directory
must be new. Input reads reject symlinks, nonregular files, duplicate JSON keys,
invalid UTF-8, nonfinite numbers and oversized data. The existing replacement
validator owns proposal identity, allowed paths, exact source hashes and caps.

The pack contains the original snapshot and proposal, replacement texts, a
representational diff, inert facts, result metadata and `bundle.json`. The latter
is written last and hashes every other artifact. A failed publication can leave
an incomplete private directory. Do not treat a directory without a valid
`bundle.json` as a finished pack. A successful CLI prints `status: finalized`;
that means packaging finished, while the pack's status remains `review_required`.

Source text is included. There is no secret redaction. Keep packs private. Raw
provider logs, credentials and unrelated context do not belong in these inputs.
The importer deliberately does not verify approval, live Git HEAD, snapshot
provenance, the existing task's current state or remaining repair budget. Verify
those through the existing workflow before using any proposed change. It creates
no attempt authorization and cannot replace the gate ledger or independent
review. Hashes detect changed bytes; they do not establish authority or protect
against a hostile process with the same account access. There is no apply step.

Exit codes: 0 for a finalized review pack, 2 for invalid input, 3 for publication
failure. Diagnostics contain fixed status codes, not source-bearing exceptions.
