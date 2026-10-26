"""Disposable loopback hosted-mode fixture. Never starts a worker or a public tunnel."""
import argparse
import hashlib
import json
import os
import socket
import tempfile
from pathlib import Path

import uvicorn

from physimesh.api.app import create_app
from physimesh.api.settings import Settings
from physimesh.platform.identity import Principal
from physimesh.platform.scoped_artifacts import artifact_scope
from physimesh.projects.reports import report_identity

parser = argparse.ArgumentParser()
parser.add_argument("--runtime", required=True)
args = parser.parse_args()
if os.environ.get("PHYSIMESH_BROWSER_DISPOSABLE") != "1":
    raise RuntimeError("Explicit disposable-fixture flag required")
workspace = Path(__file__).resolve().parents[2]
runtime = Path(args.runtime).resolve()
if runtime.parent != workspace / ".backend":
    raise RuntimeError("Runtime receipt must be inside this checkout's .backend directory")
root = Path(tempfile.mkdtemp(prefix="job-activity-", dir=workspace / ".backend"))
app = create_app(Settings(root, root / "jobs.sqlite", "", None, hosted_mode=True))
identity, jobs = app.state.identity, app.state.jobs
password = "synthetic-job-fixture-password"
uid = identity.provision("owner@example.test", password=password)
viewer = identity.provision("viewer@example.test", password=password)
owner = Principal(uid, "owner@example.test")
organization = identity.organization(uid, "Synthetic job activity fixture")
project = app.state.projects.create("Synthetic job recovery design")
pid = project["project_id"]
identity.claim_project(owner, organization, pid)
invitation = identity.invite(owner, pid, "viewer@example.test", "viewer")
identity.accept(Principal(viewer, "viewer@example.test"), invitation["invitation_token"])
other = app.state.projects.create("Other synthetic project")
identity.claim_project(owner, organization, other["project_id"])

with artifact_scope(pid):
    frozen = app.state.projects.freeze(pid, project["draft_version"], "screening")
    retained = app.state.studies.run(pid, frozen["revision_sha256"])
    raw = app.state.studies.export(pid, retained["study_sha256"])
    study_job = jobs.submit(pid, "study", {"revision_sha256": frozen["revision_sha256"]})
    claim = jobs.claim("synthetic-study-fixture")
    jobs.complete(claim, {"study_sha256": retained["study_sha256"],
                          "artifact_sha256": hashlib.sha256(raw).hexdigest()})
    pdf, _receipt = app.state.studies.pdf(pid, retained["study_sha256"])
    report_raw, snapshot = app.state.studies.report_inputs(pid, retained["study_sha256"])
    report = report_identity(report_raw, snapshot)
    report_job = jobs.submit(pid, "report", {"study_sha256": retained["study_sha256"], "report_identity": report})
    claim = jobs.claim("synthetic-report-fixture")
    jobs.complete(claim, {"artifact_sha256": hashlib.sha256(pdf).hexdigest(), "report_identity": report})

def submit(tag):
    return jobs.submit(pid, "study", {"revision_sha256": frozen["revision_sha256"], "synthetic_fixture": tag})

failed = submit("failed")
claim = jobs.claim("synthetic-failure-fixture")
jobs.heartbeat(claim, .125, "Synthetic input/storage refusal; no aircraft prediction")
jobs.fail(claim, "Synthetic recorded failure <script>not executable</script>", retry=False)
running = submit("running")
claim = jobs.claim("synthetic-explicit-retry-fixture")
jobs.fail(claim, "Synthetic first attempt failure", retry=False)
jobs.retry(pid, running["job_id"])
claim = jobs.claim("synthetic-running-fixture")
jobs.heartbeat(claim, .375, "Synthetic worker progress, not a time estimate")
cancelled = submit("cancelled")
jobs.cancel(pid, cancelled["job_id"])
queued = submit("queued")
for index in range(27):
    row = submit("older-history-" + str(index))
    jobs.cancel(pid, row["job_id"])
private = jobs.submit(other["project_id"], "study", {"revision_sha256": "a" * 64})

sock = socket.socket()
sock.bind(("127.0.0.1", 0))
sock.listen(128)
base = "http://127.0.0.1:" + str(sock.getsockname()[1])
record = {"base": base, "root": str(root), "pid": os.getpid(), "project_id": pid,
          "other_project_id": other["project_id"], "private_job_id": private["job_id"],
          "study_sha256": retained["study_sha256"], "revision_sha256": frozen["revision_sha256"],
          "jobs": {"succeeded": study_job["job_id"], "report": report_job["job_id"],
                   "failed": failed["job_id"], "running": running["job_id"],
                   "queued": queued["job_id"], "cancelled": cancelled["job_id"]}}
runtime.write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps({"base": base, "runtime": str(runtime), "pid": os.getpid()}), flush=True)
uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])
