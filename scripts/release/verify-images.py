"""Verify the actual application/worker images with private synthetic jobs."""

import hashlib
import json
import secrets
import socket
import subprocess
import time
from pathlib import Path

import httpx

root = Path.cwd()
revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
images = {kind: "physimesh-" + kind + ":" + revision for kind in ("application", "worker")}
data = root / ".backend/image-smoke" / secrets.token_hex(6)
data.mkdir(parents=True, mode=0o777)
data.chmod(0o777)
envfile = data.parent / (data.name + ".env")
envfile.touch(mode=0o600)
envfile.write_text("PHYSIMESH_MODE=hosted\nPHYSIMESH_DATA_ROOT=/data\nPHYSIMESH_DB_PATH=/data/jobs.sqlite\n")
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
containers = []
options = [
    "--read-only",
    "--user",
    "10001:10001",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
    "--cpus",
    "2",
    "--memory",
    "2g",
    "--pids-limit",
    "128",
    "--tmpfs",
    "/tmp:rw,size=128m,uid=10001,gid=10001",
    "--env-file",
    str(envfile),
    "--mount",
    f"type=bind,src={data},dst=/data",
]


def launch(kind):
    name = "physimesh-image-qa-" + secrets.token_hex(5)
    command = ["docker", "run", "--detach", "--name", name, *options]
    if kind == "application":
        command += ["--publish", f"127.0.0.1:{port}:8000"]
    command += [images[kind]]
    subprocess.run(command, capture_output=True, text=True, check=True)
    containers.append(name)
    return name


app = launch("application")
try:
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60, trust_env=False)
    started = time.perf_counter()
    for _ in range(200):
        try:
            health = client.get("/api/health")
            if health.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    else:
        raise RuntimeError("restricted application image readiness failed")
    startup = time.perf_counter() - started
    password = secrets.token_urlsafe(24)
    # Fixture provisioning through stdin; no credentials in command args or output.
    script = (
        'import json\nfrom physimesh.api.app import app_from_environment\na=app_from_environment()\nu=a.state.identity.provision("image@example.test",password='
        + repr(password)
        + ')\nprint(json.dumps({"org_id":a.state.identity.organization(u,"Synthetic image QA")}))\na.state.metadata.close()\n'
    )
    provision = subprocess.run(
        ["docker", "exec", "-i", app, "python", "-"], input=script, text=True, capture_output=True, check=True
    )
    org = json.loads(provision.stdout)["org_id"]
    login = client.post(
        "/api/drone/platform/login", json={"email": "image@example.test", "password": password}
    )
    login.raise_for_status()
    client.headers.update({"Authorization": "Bearer " + login.json()["token"], "X-Organization-ID": org})

    def request(method, path, **kw):
        response = client.request(method, path, **kw)
        response.raise_for_status()
        return response

    assert b'id="projects"' in request("GET", "/web/workbench.html").content
    project = request("POST", "/api/drone/projects/examples/realistic").json()
    base = "/api/drone/projects/" + project["project_id"]
    revision_record = request(
        "POST", base + "/revisions", json={"expected_version": project["draft_version"]}
    ).json()
    submitted = request(
        "POST", base + "/studies", json={"revision_sha256": revision_record["revision_sha256"]}
    )
    assert submitted.status_code == 202
    worker = launch("worker")

    def wait(job):
        for _ in range(240):
            accepted = request("GET", base + "/jobs/" + job["job_id"]).json()
            if accepted["state"] == "succeeded":
                return json.loads(accepted["result_json"])
            assert accepted["state"] not in ("failed", "cancelled"), accepted["reason"]
            time.sleep(0.25)
        raise RuntimeError("restricted image job did not finish")

    accepted = wait(submitted.json())
    study_path = base + "/studies/" + accepted["study_sha256"]
    study = request("GET", study_path).json()
    assert study["outcome"] == "feasible" and abs(study["payload_lower_bound_kg"] - 4.2531506527296115) < 1e-7
    first = request("GET", study_path + "/pdf")
    assert first.status_code == 202
    wait(first.json())
    pdf = request("GET", study_path + "/pdf").content
    assert pdf.startswith(b"%PDF-") and request("GET", study_path + "/pdf").content == pdf
    receipt = {
        "revision": revision,
        "application_build": health.json()["build"],
        "api_startup_s": startup,
        "installed_image_journey": "passed",
        "restrictions": "uid 10001, read-only root, no capabilities, bounded CPU/RAM/PIDs/tmpfs, loopback only",
        "worker_resources": accepted["resources"],
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "images": {
            kind: json.loads(subprocess.check_output(["docker", "image", "inspect", tag], text=True))[0]["Id"]
            for kind, tag in images.items()
        },
    }
    Path(".backend/image-verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
finally:
    for container in containers:
        log = subprocess.run(["docker", "logs", container], check=False, capture_output=True)
        (data / (container + ".log")).write_bytes(log.stdout + log.stderr)
        subprocess.run(["docker", "rm", "-f", container], check=False, capture_output=True)
    envfile.unlink(missing_ok=True)
