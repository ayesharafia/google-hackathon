"""Versioned gate execution through the existing ledger. No repair or completion.

Manifest execution is local verification, not a source of approval or authority.
A successful run still stops at independent review. No review is self-issued.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {"python", "python3", "pytest", "ruff", "node", "npm", "npx"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_file(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("unsafe source path")
    result = root / path
    if result.is_symlink() or not result.resolve().is_relative_to(root.resolve()) or not result.is_file():
        raise ValueError("source missing, symlink or outside repository")
    return result


def validate(manifest: dict) -> None:
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "sources", "gates", "max_repair_attempts", "review_required"}:
        raise ValueError("unknown or missing manifest fields")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("unsupported gate manifest version")
    if manifest["review_required"] is not True:
        raise ValueError("independent review must remain required")
    budget = manifest["max_repair_attempts"]
    if type(budget) is not int or not 0 <= budget <= 2:
        raise ValueError("repair budget must be 0..2")
    if not isinstance(manifest["sources"], dict) or not manifest["sources"]:
        raise ValueError("nonempty source hashes required")
    for name, sha in manifest["sources"].items():
        if not isinstance(name, str) or not isinstance(sha, str) or len(sha) != 64:
            raise ValueError("invalid source hash")
        int(sha, 16)
    gates = manifest["gates"]
    if not isinstance(gates, list) or not gates or len(gates) > 20:
        raise ValueError("1..20 gates required")
    names = set()
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != {"id", "argv", "timeout_seconds"}:
            raise ValueError("invalid gate fields")
        name, argv, timeout = gate["id"], gate["argv"], gate["timeout_seconds"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("invalid or duplicate gate ID")
        names.add(name)
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            raise ValueError("invalid gate command")
        if argv[0] not in ALLOWED or any(x in {"|", ";", "&&", ">", "<"} for x in argv):
            raise ValueError("command outside verification allowlist")
        if type(timeout) is not int or not 1 <= timeout <= 600:
            raise ValueError("timeout must be 1..600")


def evaluate(root: Path, manifest: dict, task: str, attempt: int = 0, run=subprocess.run) -> dict:
    validate(manifest)
    result = {"schema_version": 1, "task": task, "status": "blocked", "gates": [],
              "repair_attempt": attempt, "review_required": True, "completion_allowed": False,
              "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()}
    if type(attempt) is not int or not 0 <= attempt <= manifest["max_repair_attempts"]:
        result["reason"] = "repair budget exhausted or invalid attempt"
        return result
    try:
        hashes = {name: digest(source_file(root, name)) for name in manifest["sources"]}
    except (ValueError, OSError):
        result["reason"] = "source verification unavailable"
        return result
    result["source_sha256"] = hashes
    if hashes != manifest["sources"]:
        result["reason"] = "source hashes changed; refresh scope and review"
        return result
    environment = dict(os.environ)
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    environment["PYTHONPATH"] = str(root / "src")
    try:
        queue = json.loads(source_file(root, ".physicore/ops/TASKS.json").read_text())
        active = next(t for t in queue["tasks"] if t["id"] == task)
        if active["status"] != "in_progress" or not active.get("started_at"):
            raise ValueError("task not active")
    except (OSError, ValueError, TypeError, KeyError, StopIteration):
        result["reason"] = "active existing-ledger task unavailable"
        return result
    try:
        reservation = run(
            [sys.executable, str(root / ".physicore/tools/workflow.py"), "reserve-gate-attempt", task,
             "--attempt", str(attempt), "--budget", str(manifest["max_repair_attempts"])],
            cwd=root, env=environment, timeout=30, capture_output=True, text=True, check=False,
        )
        if reservation.returncode:
            raise ValueError("reservation refused")
        reserved = json.loads(reservation.stdout)
        if (reserved.get("attempt") != attempt or reserved.get("started_at") != active["started_at"]
                or reserved.get("max_repair_attempts") != manifest["max_repair_attempts"]):
            raise ValueError("reservation mismatch")
        result["reservation"] = reserved
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
        result["reason"] = "durable gate attempt unavailable, replayed or exhausted"
        return result
    for gate in manifest["gates"]:
        prior = {p.resolve() for p in (root / ".physicore/evidence").rglob("*") if p.is_file()}
        try:
            completed = run(
                [sys.executable, str(root / ".physicore/tools/workflow.py"), "check", "--timeout",
                 str(gate["timeout_seconds"]), "--gate-start", active["started_at"], "--gate-attempt", str(attempt), task, "--", *gate["argv"]],
                cwd=root, env=environment, timeout=gate["timeout_seconds"] + 30,
                capture_output=True, text=True, check=False,
            )
            # Retain the existing collector's receipt reference, never raw output.
            tokens = completed.stdout.strip().split()
            receipt = tokens[2] if len(tokens) == 3 and tokens[:2] in [["TEST", "PASS"], ["TEST", "FAIL"]] else None
            record = json.loads(source_file(root, receipt).read_text()) if receipt else None
            if (not isinstance(record, dict) or source_file(root, receipt).resolve() in prior
                    or record.get("id") != task or record.get("argv") != gate["argv"]
                    or record.get("started_at") != active["started_at"]
                    or record.get("repo") != str(root)
                    or type(record.get("returncode")) is not int):
                raise ValueError("missing or mismatched workflow receipt")
            rc = record.get("returncode")
            status = "passed" if rc == 0 and completed.returncode == 0 else "failed"
            result["gates"].append({"id": gate["id"], "status": status, "receipt": receipt,
                                    "returncode": rc, "timed_out": rc == 124})
            if status == "failed":
                result.update(status="failed", reason="gate failed; repair and new review required")
                return result
        except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError):
            result["gates"].append({"id": gate["id"], "status": "blocked"})
            result["reason"] = "workflow unavailable, outer timeout or receipt mismatch"
            return result
        try:
            changed = any(digest(source_file(root, name)) != sha for name, sha in hashes.items())
        except (OSError, ValueError):
            changed = True
        if changed:
            result["reason"] = "source changed during verification"
            return result
    result.update(reason="checks passed; independent review and completion remain separate", ready_for_review=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--repair-attempt", type=int, default=0)
    args = parser.parse_args()
    try:
        manifest = json.loads(source_file(ROOT, args.manifest).read_text())
        result = evaluate(ROOT, manifest, args.task, args.repair_attempt)
    except (OSError, ValueError, TypeError):
        print("BLOCKED: invalid or unavailable gate manifest", file=sys.stderr)
        return 2
    # A retained check result is not approval, proof or ledger completion.
    import datetime as dt
    destination = ROOT / ".physicore/evidence" / ("gates-" + dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S%f") + ".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(result["status"].upper(), destination.relative_to(ROOT))
    return 1 if result["status"] == "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
