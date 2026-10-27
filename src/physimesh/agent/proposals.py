"""Deterministic units and edits; user values never become measured provenance."""

import json
import math

from physimesh.drone.snapshot_hash import snapshot_sha256
from physimesh.projects.contracts import parse_snapshot, snapshot_json
from physimesh.projects.repository import DraftConflict, ProjectMissing

from .store import encoded, uid


def view(row):
    return {
        "proposal_id": row["proposal_id"],
        "project_id": row["project_id"],
        "expected_version": row["expected_version"],
        "expires": row["expires"],
        "changes": json.loads(row["changes_json"]),
        "applied_version": row["applied_version"],
        "undo_version": row["undo_version"],
        "before_sha256": snapshot_sha256(parse_snapshot(row["before_json"])),
        "after_sha256": snapshot_sha256(parse_snapshot(row["after_json"])),
        "qualification": "User-declared inputs; no scientific acceptance.",
    }


def read(db, project_id, proposal_id):
    row = db.execute(
        "SELECT * FROM agent_proposals WHERE proposal_id=? AND project_id=?", (proposal_id, project_id)
    ).fetchone()
    if row is None:
        raise ProjectMissing("proposal not found in this project")
    return row


def create(app, store, ctx, args):
    project = app.state.projects.repository.get(args.project_id)
    if project["draft_version"] != args.expected_version:
        raise DraftConflict(project["draft_version"])
    before = project["snapshot_json"]
    data = parse_snapshot(before)
    changes, seen = [], set()
    for edit in args.edits:
        key = (edit.field, edit.item_name)
        if key in seen:
            raise ValueError("a field can appear only once in one proposal")
        seen.add(key)
        if edit.field.startswith("mission."):
            if edit.item_name is not None:
                raise ValueError("mission fields do not take an item name")
            target, field = data["mission"], edit.field.split(".")[1]
        else:
            matches = [r for r in data["masses"]["items"] if r.get("name") == edit.item_name]
            if edit.item_name is None or len(matches) != 1:
                raise ValueError("mass edits require one exact, uniquely named existing item")
            target, field = matches[0], edit.field
        if field == "duration_s":
            factors, unit = {"s": 1, "min": 60}, "s"
        elif field == "cg_body_m":
            factors, unit = {"m": 1, "cm": 0.01, "mm": 0.001}, "m"
        else:
            factors, unit = {"kg": 1, "g": 0.001}, "kg"
        if edit.unit not in factors:
            raise ValueError("unit does not match the selected field")
        if field == "cg_body_m":
            if not isinstance(edit.value, list) or len(edit.value) != 3:
                raise ValueError("CG requires exactly three body-frame coordinates")
            value = [x * factors[edit.unit] for x in edit.value]
        else:
            if isinstance(edit.value, list) or edit.value < 0 or (field == "duration_s" and edit.value <= 0):
                raise ValueError("mass must be nonnegative; duration must be positive")
            value = edit.value * factors[edit.unit]
        if not all(math.isfinite(v) for v in (value if isinstance(value, list) else [value])):
            raise ValueError("converted quantity is not finite")
        changes.append(
            {
                "field": edit.field,
                "item_name": edit.item_name,
                "before": target.get(field),
                "after": value,
                "unit": unit,
                "declared_value": edit.value,
                "declared_unit": edit.unit,
            }
        )
        target[field] = value
    after = snapshot_json(data)
    app.state.projects.validate_snapshot(after)
    proposal_id = uid("proposal")
    with store.database.connection(write=True) as db:
        store.lock(db)
        store.quota(
            db,
            "agent_proposals",
            args.project_id,
            len(before.encode()) + len(after.encode()) + len(encoded(changes).encode()),
        )
        db.execute(
            "INSERT INTO agent_proposals VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                proposal_id,
                args.project_id,
                ctx.actor,
                before,
                after,
                args.expected_version,
                store.clock() + 900,
                encoded(changes),
                None,
                None,
                None,
            ),
        )
        return view(read(db, args.project_id, proposal_id))


def preview(app, store, action, args):
    with store.database.connection() as db:
        row = read(db, args.project_id, args.proposal_id)
        result = view(row)
    project = app.state.projects.repository.get(args.project_id)
    undo = action == "proposal.undo"
    expected = row["applied_version"] if undo else row["expected_version"]
    if not undo and (row["expires"] <= store.clock() or row["applied_version"] is not None):
        raise ValueError("proposal expired or already applied; prepare a fresh proposal")
    if undo and (expected is None or row["undo_version"] is not None):
        raise ValueError("proposal has no eligible application to undo")
    original = row["after_json"] if undo else row["before_json"]
    if project["draft_version"] != expected or project["snapshot_json"] != original:
        raise DraftConflict(project["draft_version"])
    result["operation"] = "undo" if undo else "apply"
    result["expected_current_version"] = expected
    return result


def apply(app, store, db, action, args):
    row = read(db, args.project_id, args.proposal_id)
    undo = action == "proposal.undo"
    if not undo and (row["expires"] <= store.clock() or row["applied_version"] is not None):
        raise ValueError("proposal expired or already applied")
    if undo and (row["applied_version"] is None or row["undo_version"] is not None):
        raise ValueError("proposal cannot be undone")
    current = app.state.projects.repository._row(db, args.project_id)
    expected = row["applied_version"] if undo else row["expected_version"]
    original = row["after_json"] if undo else row["before_json"]
    if current["version"] != expected or current["snapshot"] != original:
        raise DraftConflict(current["version"])
    raw = row["before_json"] if undo else row["after_json"]
    saved = app.state.projects.repository.save_in_transaction(db, args.project_id, expected, raw)
    if undo:
        db.execute(
            "UPDATE agent_proposals SET undo_version=? WHERE proposal_id=?",
            (saved["draft_version"], args.proposal_id),
        )
    else:
        db.execute(
            "UPDATE agent_proposals SET applied_version=?,applied_hash=? WHERE proposal_id=?",
            (saved["draft_version"], snapshot_sha256(parse_snapshot(raw)), args.proposal_id),
        )
    return {
        "project_id": args.project_id,
        "proposal_id": args.proposal_id,
        "draft_version": saved["draft_version"],
        "snapshot_sha256": snapshot_sha256(parse_snapshot(raw)),
        "operation": "undo" if undo else "apply",
    }
