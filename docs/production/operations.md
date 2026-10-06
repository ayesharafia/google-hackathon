# Private platform operation and release scope

This branch provides a local integration platform for the existing analytic V4
profile. It does not qualify new physics or constitute a production deployment.
`plan.md` holds status and gates; this document holds operating instructions.

## Reproduce and run

Use Linux/Python 3.11.16. Install `requirements-test.lock` with hash verification,
then `pip install --no-deps -e .`. Run unit/reference tests, the hosted smoke,
PostgreSQL integration helper and browser scripts described in CI. PostgreSQL and
S3-compatible adapters are optional in local mode; `PHYSIMESH_MODE=local` uses the
explicit local bearer token and SQLite. Never expose that shared-token profile as
an individual private workspace.

For a release, commit the sources first; export the immutable Python base in
`deployment/images.env`, then run `scripts/release/build-images.sh` with the
locked build environment. Runtime wheels are hash-verified, downloaded before
building, and installed offline. The application wheel includes web assets,
schemas, solver templates, dependency identity and a verified source manifest.
Use matching application/worker build digests. A job retains its build identity;
workers from another release cannot claim it. Historical result bytes and model
contracts are retained unchanged.

The private Compose template publishes no host ports. It requires a pre-owned
private data volume, immutable images and an operator-owned environment file.
Before use, supply PostgreSQL, private S3 bucket/region/HTTPS endpoint (or cloud
SDK role), OIDC HTTPS issuer/JWKS and audience, and a separate monitoring token.
Decide private TLS ingress, residency, MFA, invitation policy, retention, scale,
backup ownership and budget (D01-D03/D07) before external deployment. The local
credential adapter is for controlled integration; production users should be
provisioned against the selected IdP subject. Browser OIDC authorization-code/PKCE
integration awaits that policy; the API accepts verified, pre-provisioned subjects.

Trusted operator provisioning is `python -m physimesh.platform.cli`; password
fixtures use `PHYSIMESH_PROVISION_PASSWORD`, never command arguments or logs.
There is no anonymous registration. Organizations own projects. Engineer can
edit/run; viewer can inspect/download/compare; reviewer can add authenticated
review decisions. Organization admins administer membership. Reviews bind exact
result bytes and an actor, and never promote model or aircraft qualification.
One-use, email-bound invitations are shared through an approved client channel;
the application does not send unsolicited messages.

## Capacity and recovery

Metadata uses bounded pools (default eight), two-second lock/pool waits and short
transactions. Overload is explicit HTTP 503 with retry guidance. Application JSON
and import bytes, inventories, histories, project counts, artifacts and queue
admissions are bounded. Default job admission is 256 globally/eight per project;
four claims may run. Study/report attempts have 30-second leases, at most three
automatic attempts, and explicit cancellation/retry. Build-matched workers renew
leases; expired generations cannot publish. The accepted job receipt is immutable;
project materialization can be retried from that receipt after a crash.

Children have hard 60-second CPU, 2 GiB virtual-memory and 5 MB file limits;
supervisors enforce 120-second wall, 2 GiB RSS and 20 MB attempt-directory limits.
Children die on supervisor death. Compose adds CPU/RAM/PID bounds and a read-only
root filesystem. No user commands or Docker socket enter study/report workers.
Legacy CFD endpoints are denied in hosted mode until their project ownership and
isolated durable worker integration are implemented. Native CFD remains available
in the explicit local supported profile.

`/internal/metrics` requires the separate monitoring credential; it is disabled
without one. It exposes route-template latency histograms, process CPU/RSS and
job states, with no project IDs/emails/token labels. Protect metrics at ingress;
alert on failed/expired attempts, oldest queued job, saturation, artifact errors,
connection errors, memory growth and disk capacity. Detailed attempt logs remain
private artifacts. Define operational audit retention and alert delivery after
provider selection. Local adapters do not establish global IdP/ingress rate limits.

## Backup, restore and rollback

For local platform snapshots, stop API/workers, then use `backup_local(data_root,
new_backup_root)` from `physimesh.platform.backup`. Keep its returned manifest
SHA-256 in a separate trusted record. `restore_local(backup, fresh_root,
manifest_sha256=...)` rejects missing, corrupt, unlisted or escaping files and
checks SQLite integrity. It never overwrites live data. Verify historical study,
PDF and authorized project access from the restored root before switching it in.
This helper covers projects/platform metadata and immutable artifacts; legacy CFD
case directories/jobs require their own retained archive. It is not a remote
PostgreSQL/S3 snapshot facility or a hosted RPO/RTO demonstration.

For hosted operation, preregister coordinated PostgreSQL PITR and versioned private
object-store backup schedules, encryption, retention and recovery owner. Restore
into an isolated environment, verify all referenced object hashes and role grants,
then exercise studies/reports and worker recovery. Measure recovery point/time;
RPO 15 minutes and RTO 60 minutes remain proposed, unproved targets.

Migrations run transactionally with advisory locking and reject unknown future
versions (SQLite projects v3; PostgreSQL project migration v1; platform v1-v5).
Back up before upgrade. Drain old-build jobs with old workers before retiring their
image; new workers do not silently reinterpret old specifications. Rollback means
restoring a tested compatible snapshot and matching old image, not downgrading a
new schema in place. Review jobs accepted after the snapshot before cutover.
Exercise this against the chosen hosted provider before any production release.

## Engineering limitations

Current numerical code and historical evidence remain the supported simpler
profile. Endpoint roundoff and the conditioning-conservatism argument require the
recorded independent review and human engineering acceptance. Stateful batteries,
mission transitions, general-curve MILP, forward-flight trim, dynamic fault control,
design exploration and installed CFD remain review/validation-gated follow-ons.
Real measured maps, aircraft inputs and a named engineering owner are unavailable.
Synthetic passing tests never establish aircraft accuracy or dynamic controllability.
