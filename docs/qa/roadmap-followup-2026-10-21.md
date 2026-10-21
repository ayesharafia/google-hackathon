# Roadmap QA follow-up — 21 October 2026

This continuation starts from PR #19 at `edf5beb04665c1f0f0d43256864971f6a0f4fccb`.
A05, A06 and A07 were already implemented in PRs #16–#18; they were reused rather
than duplicated. [Draft PR #20](https://github.com/PhysiCoreEngine12/Drone-Project/pull/20)
is stacked on PR #19. No merge, release or deployment is performed.

## Changes and incremental publication

- `45952fb`: normalize electrical inventory before checking its pack-mode binding.
  Missing/malformed electrical metadata still reports electrical gaps, while a
  valid bound mission declaration remains valid. Six regression cases reproduce
  the original false mission-contract refusal.
- `4d5c89c`: retain ledger cleanup and observations when process reaping times out.
  A trusted subprocess handle receives one bounded kill/reap retry. Persistent
  timeout/OS errors remain explicit and prevent a successful CLI result. Two
  delayed-reap regression cases and a failing-CLI receipt test cover this path.
- CI now runs the actual disk-pressure drill, complete synthetic intake report,
  and one monitored study/PDF journey; receipts upload even when a later step fails.
  The soak has a 30-second workload budget, 32-request/one-journey caps, and sampled
  64 MiB storage/1 GiB memory stop thresholds. These are not hard OS quotas.

The first two fixes were committed and pushed separately before this evidence/CI
increment, as requested. No source under `src/` or `web/` differs from PR #19;
all 18 declared numerical-model modules were also compared byte-for-byte.

## Actual execution

Python **3.11.16**; missing dependencies were installed from the hash-verified
`requirements-test.lock` (SHA-256
`10bb3d0ce1593af4d308280d44efa33eb976836aaf3d9827ddf67a71f4f5e9d1`).
An initial test collection failed because this restored environment lacked boto3;
that setup problem was resolved before final verification.

| Performed check | Result |
|---|---|
| Full non-backend/non-integration suite | 615 passed, 5 deselected |
| Reference suite | 118 passed |
| Intake helper tests | 32 passed; independently rerun by a peer |
| Soak helper tests | 26 passed; peer reviewed the change and independently verified CLI failure receipt |
| Ruff and whitespace | Passed |
| Actual complete intake CLI | Exit 0, declaration-only report |
| Actual incomplete intake CLI | Exit 1, explicit gaps retained |
| Actual injected storage-refusal drill | Both object/metadata failures recovered; retry, lease recovery, stale-publication denial and cleanup passed |
| Exact CI normal soak command | One study/PDF journey, 13 requests, two accepted jobs, exit 0 |

The [full sanitized soak receipt](soak-harness-2026-10-21.json) retains source hashes,
runtime, request observations and resource samples for five post-setup campaigns:

| Campaign | Observed behavior |
|---|---|
| Normal | One synthetic study/PDF journey in 4.709 seconds; 13 requests, two accepted jobs |
| Two-second duration stop | One running job cancelled, one stale completion refused; 2.020 seconds including cleanup |
| Storage threshold | Stopped at first observed write exceeding the deliberately tiny threshold |
| Memory threshold | Stopped at first observed RSS exceeding the deliberately tiny threshold |
| SIGINT | Interrupted the fifth request before admission committed; no accepted-job fencing claim for this run |

Every campaign observed zero surviving owned processes, no cleanup error and
removal of its disposable directory. The namespace guard refused execution on
14 October; this environment now has compatible process namespaces and the guarded
run actually executed. Historical guard evidence was preserved unchanged.

Implementation and QA used actual `intake_v2`, `soak_v2` and `recovery_v2` agents.
The intake and soak changes received separate peer review; these are same-family
software checks, not independent cross-family model acceptance or human approval.
The superseded duplicate recovery drafts were kept outside the repository.

## Remaining limits

This short campaign is not a 24-hour soak, provider recovery qualification,
production latency result, hard resource quota test or aircraft validation.
PostgreSQL, browser, installed-wheel/image and pinned OpenFOAM backend checks were
not rerun locally for this QA-only change. The five deselections are not passes.
GitHub CI results for this exact head are recorded separately when available;
the prior PR #19 CI results remain historical evidence. Model review, named human
engineering acceptance, real client inputs, hosted CFD ownership, submission
latency qualification and hosting decisions remain open in `plan.md`.
