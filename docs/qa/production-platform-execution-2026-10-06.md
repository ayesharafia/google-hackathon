# Production platform execution evidence, 6 October 2026

Implemented on `codex/production-platform`, stacked on the unapproved current
model branch. `plan.md` is the single status tracker. This is fixture-driven
software evidence, not a production release or aircraft qualification.

The branch provides bounded project inventory/history; accepted-study reuse after
source checks; immutable verified PDF receipts; PostgreSQL and private S3-compatible
adapters; versioned migrations; individual revocable sessions and OIDC verification;
organizations/project roles; email-bound one-use invitations; authenticated exact-
result review records and downloads; bounded durable study/report jobs with attempts,
progress, cancellation, retries, leases and stale-worker fencing; isolated bounded
computation; protected metrics; transactional local backup and verified restore;
and packaged resources, locked runtime wheels and provider-neutral deployment inputs.

Numerical modules remain unchanged. Local SQLite/shared-bearer mode remains explicit.
Hosted legacy unowned CFD/global-artifact routes deny access. Private CFD job ownership,
selected-provider browser OIDC/PKCE, full audit/retention policy and hosted disaster
recovery remain follow-ons; the deployment template is not an activated deployment.

Performed checks: **529 unit tests**, **118 retained reference tests**, **two real
PostgreSQL integration tests**, **one actual pinned sphere backend smoke**, Ruff and
JavaScript syntax checks. Integration includes 50 independent concurrent saves and
50 same-version contenders (one succeeds, 49 explicit conflicts). Private-object
checks use an actual local Moto HTTP service, conditional writes, corruption and
public policy/ACL refusal; this is not a production bucket audit. JWT tests use
real RSA signatures with issuer/audience/expiry/algorithm negatives and revocation.

Browser evidence: [local journey](assets/production-release-local/receipt.json)
(11 screenshots; native 200% zoom, mobile, conflicts, full analytic workflow and
downloads) and [private journey](assets/production-hosted/receipt.json)
(sign-in, project isolation, queued study/PDF, viewer/reviewer write denial,
authenticated review and JSON download, 390 px layout, revoked session preserving
inputs). The [actual worker failure drill](production-worker-failure-2026-10-06.json)
kills a supervisor and observes child death, accelerates the retained lease expiry,
restarts a worker, rejects stale publication, reopens accepted evidence and refuses
a deliberately tiny wall budget. It does not pretend to wait through a natural
30-second lease expiry.

The [fresh pre-change V4 baseline](production-baseline-2026-10-06.md) retains three
runs per workload at 1/10/25/50 users, five cold starts and six unchanged pinned
coarse/medium sphere pipelines plus six native postprocessing measurements. The
baseline archive contains sanitized metrics/request samples, not credentials,
databases or private service state. [The repeat audit](production-performance-2026-10-06.md) retains all local overloads
and separate cold/warm export and PostgreSQL trials at 1/10/25/50 users. All three
PostgreSQL save/submission repeats completed without failures. At 50 users, median
trial save p95 is 582 ms; submission p95 is 592 ms, above the proposed 250 ms target.
The 303.8-second single-client soak completed 67 distinct study/PDF journeys without
failures or lost accepted jobs; it does not establish the proposed 24-hour target.
Clean installed-wheel and restricted application/worker image journeys passed;
final image reproducibility checks are in progress.

Independent current-model review and human engineering acceptance remain required
before physics extension/merge/tag; see the [review packet](production-model-review-packet.md).
U05 is authorized but follows that gate. Hosting/region/budget, identity/MFA,
confidentiality/residency, scale and the named engineering owner remain undecided.
Real aircraft data is unavailable. No external access link, main-branch merge,
installed-aircraft CFD, full stateful mission engine or real engineering claim is
asserted by these platform checks.
