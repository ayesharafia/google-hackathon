# PhysiCore Autonomy Portfolio v3 adoption

Date: 22 October 2026. The owner explicitly requested replacing the previous
instructions with `PhysiCore_Autonomy_Portfolio_v3.zip` and publishing to GitHub.
Source baseline: `cdee01b22e86724d3dc5f883295415c4b5f4e188`.

## Active setup

Installed the 19 per-repository assets and managed AGENTS bridge after reading
the directive, installer, policies and helper, and inspecting its dry-run.
Use `.physicore/ops/STATE.md`, `TASKS.json`, `WORKLOG.md` and `APPROVALS.md`.
One bounded task per broad Work prompt replaces the old three-task/fixed-team
cycle. Specialists are used when useful, rather than launched by default.
Scientific checks are applicable to the actual model and claim; past approved
thresholds, retained data and qualified-review boundaries remain intact.

The installation is limited to this known writable drone repository. The parent
directory is not a dedicated company workspace, so no sibling repositories or
HQ were modified. This is an active-session local workflow, not a background
service, paid API integration or new access to other GitHub projects.

## Retirement and continuity

Moved 28 old root policies/trackers, templates and Claude roles/commands to
`.physicore/legacy/sim-kit-2026-10-22/`. Root policy filenames now contain only
redirects, and active `.claude` role/command files are removed. Old AGENTS and
CLAUDE are named snapshots rather than automatically loaded instruction files.
Updated README, plan and roadmap pointers. Previous adoption pages are marked
historical. The append-only decision log records replacement in entry 013.

Retained existing application, tests, models, physics specs, results, project
data and all branches. Pending DR-01 review is carried into APPROVALS; no missing
approval or customer accuracy value is invented. The original backlog remains
in the inactive archive so earlier proposals are not lost.

## Source and local adaptation

The exact supplied ZIP is retained as
[PhysiCore_Autonomy_Portfolio_v3.zip](../source/PhysiCore_Autonomy_Portfolio_v3.zip).
The [migration manifest](../source/portfolio-v3-2026-10-22-manifest.json) records
source payload hashes, installed hashes and each archived file's identity.

The installed helper received repository lint compatibility adjustments only:
ordered imports, Python 3.11's UTC alias, explicit `check=False` where return
codes are already handled, `min` for first-by-key selection, and executable mode
matching its shebang. No acceptance gate or ledger behavior was intentionally
changed. Its upstream source hash remains recorded by the installer; a later
reinstall must review the intentional local helper difference rather than
silently overwrite it. No project lint rules were weakened.

## Checks and claim limits

Installer dry-run and install succeeded for one repository; workflow doctor
validated the ledger. The actual app and test scaffolding were inspected for
AUDIT-001, and hashed source observations plus a resume narrative were retained.
Ruff, local-link, ZIP/source hash and whitespace checks are recorded with the
migration evidence. No application or kit test suite, CFD campaign or external
market research was run for this configuration migration. The supplied
distribution's test-results page is an upstream claim, not a test executed here.

Historical main CI at `cdee01b` completed successfully in
[run 39765169727](https://github.com/PhysiCoreEngine12/Drone-Project/actions/runs/39765169727).
That does not validate the new helper or any aircraft. No physical accuracy,
independent scientific acceptance, release approval or deployment is conferred.
