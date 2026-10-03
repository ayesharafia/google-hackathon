#!/usr/bin/env python3
"""Verify the frozen P00.1 evidence, or launch its explicitly selected private demo."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

from physimesh.postpro.baseline import fingerprint, load_inventory, read_json, verify_baseline

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "docs/qa/production-baseline.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="Read-only check; native/vendor checks are explicit")
    verify.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    verify.add_argument("--data-root", type=Path)
    verify.add_argument("--native", action="store_true")
    verify.add_argument("--vendor", action="store_true")
    demo = sub.add_parser("demo", help="Check the reviewed preset before serving on localhost")
    demo.add_argument("--preset", type=Path, default=ROOT / "docs/demo/reviewed-demo.json")
    demo.add_argument("--data-root", type=Path)
    demo.add_argument("--port", type=int, default=8766)
    demo.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            inventory = load_inventory(args.inventory)
            report = verify_baseline(ROOT, inventory, data_root=args.data_root,
                                     native=args.native, vendor=args.vendor)
        else:
            preset = read_json(args.preset.read_bytes())
            if (not isinstance(preset, dict)
                    or set(preset) != {"schema_version", "inventory_sha256"}
                    or preset["schema_version"] != "reviewed_demo_v1"
                    or fingerprint(DEFAULT_INVENTORY).sha256 != preset["inventory_sha256"]):
                raise ValueError("reviewed-demo preset does not bind the frozen inventory")
            if not 1 <= args.port <= 65535:
                raise ValueError("port must be between 1 and 65535")
            inventory = load_inventory(DEFAULT_INVENTORY)
            report = verify_baseline(ROOT, inventory, data_root=args.data_root)
        print(json.dumps(report, indent=2), flush=True)
        if args.command != "demo" or args.check_only:
            return 0
        token = os.environ.get("PHYSIMESH_API_TOKEN") or getpass.getpass("Local demo session token: ")
        if not token.strip():
            raise ValueError("a nonblank session token is required")
        selected = (args.data_root or ROOT / inventory.package.data_root).resolve()
        env = {**os.environ, "PHYSIMESH_API_TOKEN": token, "PHYSIMESH_DATA_ROOT": str(selected),
               "PHYSIMESH_DB_PATH": str(selected / "jobs.sqlite"),
               "PHYSIMESH_OPENFOAM_IMAGE_DIGEST": inventory.image_digest, "PHYSIMESH_BIND_HOST": "127.0.0.1"}
        return subprocess.call([sys.executable, "-m", "uvicorn", "physimesh.api.app:app_from_environment",
                                "--factory", "--host", "127.0.0.1", "--port", str(args.port)], cwd=ROOT, env=env)
    except (OSError, ValueError, EOFError) as exc:
        parser.exit(2, f"Baseline refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
