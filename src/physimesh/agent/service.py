"""Action admission, trusted approval and replay-safe receipts."""

import hashlib
import json

from physimesh.drone.snapshot_hash import snapshot_sha256
from physimesh.platform.identity import Denied
from physimesh.platform.scoped_artifacts import artifact_scope
from physimesh.projects.contracts import parse_snapshot
from physimesh.projects.repository import DraftConflict, ProjectMissing

from . import contracts, operations, proposals, registry
from .policy import Policy
from .store import Store, encoded, uid


class AgentService:
    def __init__(self, app):
        self.app = app
        self.store = Store(app.state.metadata)
        self.policy = Policy(app, self.store)

    def context(self, request):
        return getattr(request.state, "agent_context", None) or self.policy.trusted(
            getattr(request.state, "principal", None)
        )

    def catalog(self, ctx, project_id=None):
        ctx = self.policy.refresh(ctx)
        pid = ctx.project_id or project_id
        actions = []
        for spec in registry.ACTIONS.values():
            if spec.group not in ctx.groups or (spec.hosted_only and not self.app.state.settings.hosted_mode):
                continue
            if pid:
                try:
                    self.policy.authorize(ctx, pid, write=spec.group != "read")
                except Denied:
                    continue
            actions.append(spec.describe())
        return {
            "schema_version": "physicore_action_catalog_v1",
            "actions": actions,
            "project_id": pid,
            "mode": "hosted" if self.app.state.settings.hosted_mode else "local",
            "pending_domains": registry.PENDING,
            "model_provider_required": False,
            "analysis_model": {
                key: value
                for key, value in self.app.state.studies.model_identity.items()
                if key in ("model_version", "source_fingerprint_sha256", "qualification")
            },
            "limits": {"inline_bytes": 262144, "bulk_entities": 25},
            "qualification": "Software interfaces; engineering acceptance remains separate.",
        }

    def _validate(self, ctx, action, arguments):
        ctx = self.policy.refresh(ctx)
        spec = registry.get(action)
        if spec.group not in ctx.groups:
            raise Denied("Action is outside this AI-client grant.")
        if spec.hosted_only and not self.app.state.settings.hosted_mode:
            raise ValueError("This action requires hosted mode.")
        args = spec.inputs.model_validate(arguments)
        pid = getattr(args, "project_id", ctx.project_id)
        if pid:
            self.policy.authorize(ctx, pid, write=spec.group != "read")
        return ctx, spec, args, pid

    def _envelope(self, action, call, receipt_id, pid, status, data):
        value = contracts.ActionResult(
            action=action,
            request_id=call.request_id,
            receipt_id=receipt_id,
            project_id=pid,
            status=status,
            data=data,
        ).model_dump(mode="json")
        encoded(value)
        return value

    def _old(self, db, ctx, request_id, fingerprint):
        review = db.execute(
            "SELECT fingerprint FROM agent_reviews WHERE actor=? AND request_id=?", (ctx.actor, request_id)
        ).fetchone()
        if review and review["fingerprint"] != fingerprint:
            raise ValueError("request_id already binds a different reviewed action")
        row = db.execute(
            "SELECT * FROM agent_calls WHERE actor=? AND request_id=?", (ctx.actor, request_id)
        ).fetchone()
        if row and row["fingerprint"] != fingerprint:
            raise ValueError("request_id already binds different arguments or client authority")
        if row:
            if row["result_json"]:
                return json.loads(row["result_json"])
            return self._envelope(
                row["action"],
                contracts.Call(request_id=request_id, arguments={}),
                row["receipt_id"],
                row["project_id"],
                "failed" if row["state"] == "failed" else "uncertain",
                {
                    "reason": row["reason"]
                    or "An admitted invocation has no terminal receipt; do not replay it."
                },
            )
        return None

    def _preview(self, action, args):
        if action in ("proposal.apply", "proposal.undo"):
            return proposals.preview(self.app, self.store, action, args)
        if action == "design.freeze":
            project = self.app.state.projects.repository.get(args.project_id)
            if project["draft_version"] != args.expected_version:
                raise DraftConflict(project["draft_version"])
            return {
                "arguments": args.model_dump(mode="json"),
                "snapshot_sha256": snapshot_sha256(parse_snapshot(project["snapshot_json"])),
                "qualification": "Freeze saves evidence; it does not approve engineering.",
            }
        if action == "study.run":
            revision = self.app.state.projects.repository.revision(args.project_id, args.revision_sha256)
            return {
                "arguments": args.model_dump(mode="json"),
                "snapshot_sha256": revision.snapshot_sha256,
                "qualification": "Existing eligible model; no aircraft validation is granted.",
            }
        return {"arguments": args.model_dump(mode="json")}

    def _review(self, ctx, spec, args, call, fingerprint, pid):
        with self.store.database.connection() as db:
            old = db.execute(
                "SELECT * FROM agent_reviews WHERE actor=? AND request_id=?", (ctx.actor, call.request_id)
            ).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise ValueError("request_id already binds a different review")
                if old["status"] in ("pending", "approved") and old["expires"] <= self.store.clock():
                    raise ValueError("review expired")
                if old["status"] not in ("pending", "approved", "consumed", "executing"):
                    raise ValueError("review is no longer applicable")
                return dict(old)
        preview = self._preview(spec.id, args)
        with self.store.database.connection(write=True) as db:
            self.store.lock(db)
            old = db.execute(
                "SELECT * FROM agent_reviews WHERE actor=? AND request_id=?", (ctx.actor, call.request_id)
            ).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise ValueError("request_id already binds a different review")
                if old["expires"] <= self.store.clock() or old["status"] not in ("pending", "approved"):
                    raise ValueError("review expired or is no longer applicable")
                return dict(old)
            self.store.quota(
                db,
                "agent_reviews",
                pid,
                len(encoded(args.model_dump(mode="json")).encode()) + len(encoded(preview).encode()),
            )
            review_id = uid("review")
            db.execute(
                "INSERT INTO agent_reviews VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    review_id,
                    ctx.actor,
                    ctx.grant_id,
                    pid,
                    spec.id,
                    call.request_id,
                    fingerprint,
                    encoded(args.model_dump(mode="json")),
                    encoded(preview),
                    "pending",
                    self.store.clock() + 900,
                ),
            )
            return dict(db.execute("SELECT * FROM agent_reviews WHERE review_id=?", (review_id,)).fetchone())

    def call(self, ctx, action, call):
        ctx, spec, args, pid = self._validate(ctx, action, call.arguments)
        fingerprint = self.store.fingerprint(ctx, action, args.model_dump(mode="json"))
        with self.store.database.connection() as db:
            old = self._old(db, ctx, call.request_id, fingerprint)
        if old:
            return old
        self.policy.count_call(ctx)
        with artifact_scope(pid):
            review = self._review(ctx, spec, args, call, fingerprint, pid) if spec.approval else None
            if review and review["status"] in ("consumed", "executing"):
                with self.store.database.connection() as db:
                    old = self._old(db, ctx, call.request_id, fingerprint)
                if old:
                    return old
                raise ValueError("review has no applicable invocation receipt")
            if review and review["status"] != "approved":
                return self._envelope(
                    action,
                    call,
                    None,
                    pid,
                    "awaiting_review",
                    {
                        "review_id": review["review_id"],
                        "preview": json.loads(review["preview_json"]),
                        "next_step": "Review in the workbench. Repeat this action with the same request_id after confirmation.",
                    },
                )
            if action in ("proposal.apply", "proposal.undo"):
                with self.store.database.connection() as db:
                    proposal = proposals.read(db, pid, args.proposal_id)
                self.app.state.projects.validate_snapshot(
                    proposal["before_json"] if action == "proposal.undo" else proposal["after_json"]
                )
            with self.store.database.connection(write=True) as db:
                self.store.lock(db)
                old = self._old(db, ctx, call.request_id, fingerprint)
                if old:
                    return old
                self.policy.check_locked(db, ctx, pid, write=spec.group != "read")
                if review:
                    current = db.execute(
                        "SELECT * FROM agent_reviews WHERE review_id=?", (review["review_id"],)
                    ).fetchone()
                    if current["status"] != "approved" or current["expires"] <= self.store.clock():
                        raise Denied("Approval is no longer active.")
                self.store.quota(db, "agent_calls", pid)
                receipt_id = uid("receipt")
                db.execute(
                    "INSERT INTO agent_calls VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        receipt_id,
                        ctx.actor,
                        ctx.grant_id,
                        pid,
                        action,
                        call.request_id,
                        fingerprint,
                        "running",
                        None,
                        None,
                        self.store.clock(),
                    ),
                )
                if review:
                    db.execute(
                        "UPDATE agent_reviews SET status='executing' WHERE review_id=?",
                        (review["review_id"],),
                    )
                if action in ("proposal.apply", "proposal.undo"):
                    data = proposals.apply(self.app, self.store, db, action, args)
                    result = self._envelope(action, call, receipt_id, pid, "completed", data)
                    self._finish(db, receipt_id, review, result)
                    return result
            try:
                self.policy.refresh(ctx)
                data = self._perform(ctx, action, args)
                result = self._envelope(
                    action,
                    call,
                    receipt_id,
                    pid,
                    "queued"
                    if action == "study.run" and self.app.state.settings.hosted_mode
                    else "completed",
                    data,
                )
            except Exception:
                # Never replay a mutation whose side-effect/receipt boundary is unknown.
                with self.store.database.connection(write=True) as db:
                    db.execute(
                        "UPDATE agent_calls SET state=?,reason=? WHERE receipt_id=?",
                        (
                            "failed" if spec.effect == "read" else "uncertain",
                            "Invocation ended without a terminal receipt. Inspect existing records before a new approved request.",
                            receipt_id,
                        ),
                    )
                raise
            with self.store.database.connection(write=True) as db:
                self._finish(db, receipt_id, review, result)
            current = self.policy.refresh(ctx)
            if pid:
                self.policy.authorize(current, pid, write=spec.group != "read")
            return result

    def _finish(self, db, receipt_id, review, result):
        self.store.lock(db)
        raw = encoded(result)
        self.store.quota(db, "agent_calls", result["project_id"], len(raw.encode()), new_record=False)
        db.execute(
            "UPDATE agent_calls SET state=?,result_json=? WHERE receipt_id=?",
            (result["status"], raw, receipt_id),
        )
        if review:
            db.execute("UPDATE agent_reviews SET status='consumed' WHERE review_id=?", (review["review_id"],))

    def confirm(self, ctx, review_id, execute=True):
        if ctx.grant_id:
            raise Denied("AI clients cannot confirm their own actions.")
        with self.store.database.connection(write=True) as db:
            self.store.lock(db)
            row = db.execute(
                "SELECT * FROM agent_reviews WHERE review_id=? AND actor=?", (review_id, ctx.actor)
            ).fetchone()
            if row is None:
                raise ProjectMissing("review not found for this user")
            row = dict(row)
            self.policy.check_locked(db, ctx, row["project_id"], write=True)
            if row["status"] == "consumed":
                return json.loads(
                    db.execute(
                        "SELECT result_json FROM agent_calls WHERE actor=? AND request_id=?",
                        (ctx.actor, row["request_id"]),
                    ).fetchone()[0]
                )
            if row["status"] not in ("pending", "approved") or row["expires"] <= self.store.clock():
                raise ValueError("review expired or is already executing")
            db.execute("UPDATE agent_reviews SET status='approved' WHERE review_id=?", (review_id,))
        if not execute:
            return {"review_id": review_id, "status": "approved"}
        original = self.policy.grant_context(grant_id=row["grant_id"]) if row["grant_id"] else ctx
        return self.call(
            original,
            row["action"],
            contracts.Call(request_id=row["request_id"], arguments=json.loads(row["args_json"])),
        )

    def records(self, ctx, project_id):
        ctx = self.policy.refresh(ctx)
        self.policy.authorize(ctx, project_id)
        with self.store.database.connection() as db:
            calls = db.execute(
                "SELECT receipt_id,action,request_id,state,reason,created FROM agent_calls "
                "WHERE actor=? AND project_id=? ORDER BY created DESC,receipt_id LIMIT 25",
                (ctx.actor, project_id),
            ).fetchall()
            rows = db.execute(
                "SELECT review_id,action,request_id,preview_json,status,expires FROM agent_reviews "
                "WHERE actor=? AND project_id=? ORDER BY expires DESC,review_id LIMIT 25",
                (ctx.actor, project_id),
            ).fetchall()
        reviews = []
        for row in rows:
            item = dict(row)
            item["preview"] = json.loads(item.pop("preview_json"))
            reviews.append(item)
        invocations = []
        for row in calls:
            item = dict(row)
            if item["state"] == "running":
                item["state"] = "uncertain"
                item["reason"] = (
                    "No terminal receipt. Work may still be running or interrupted; inspect retained records."
                )
            invocations.append(item)
        return {"invocations": invocations, "reviews": reviews}

    def _perform(self, ctx, action, args):
        app = self.app
        repo = app.state.projects.repository
        pid = getattr(args, "project_id", ctx.project_id)
        if action == "projects.list":
            if ctx.project_id:
                p = repo.get(ctx.project_id)
                return {
                    "projects": [{k: p[k] for k in ("project_id", "title", "draft_version")}],
                    "next_cursor": None,
                }
            return repo.page(limit=25, user_id=ctx.principal.user_id if ctx.principal else None)
        if action == "design.schema":
            return {
                "schema_version": "physicore_edit_catalog_v1",
                "proposal_schema": contracts.Propose.model_json_schema(),
                "units": {"mass": ["kg", "g"], "duration": ["s", "min"], "body_position": ["m", "cm", "mm"]},
                "limits": "Only explicit user values; exact named existing mass items. No source/model/tolerance edits.",
            }
        if action == "design.get":
            return repo.get(pid)
        if action == "design.inspect":
            return operations.inspect_project(app, pid)
        if action == "design.propose":
            return proposals.create(app, self.store, ctx, args)
        if action == "proposal.get":
            with self.store.database.connection() as db:
                return proposals.view(proposals.read(db, pid, args.proposal_id))
        if action == "receipt.get":
            with self.store.database.connection() as db:
                row = db.execute(
                    "SELECT result_json,state FROM agent_calls WHERE receipt_id=? AND project_id=? AND actor=?",
                    (args.receipt_id, pid, ctx.actor),
                ).fetchone()
            if row is None:
                raise ProjectMissing("receipt not found in this actor/project scope")
            return (
                json.loads(row["result_json"])
                if row["result_json"]
                else {"status": "uncertain", "receipt_id": args.receipt_id}
            )
        if action == "design.freeze":
            return operations.freeze_project(app, pid, args.expected_version, args.purpose, ctx.principal)
        if action == "revision.get":
            return repo.revision(pid, args.revision_sha256).model_dump(mode="json")
        if action == "study.run":
            return operations.run_study(app, pid, args.revision_sha256, ctx.principal)
        if action == "study.get":
            return app.state.studies.read(pid, args.study_sha256)
        if action == "study.summary":
            return app.state.studies.summary(pid, args.study_sha256)
        if action == "study.compare":
            return operations.compare_studies(app, pid, args.before, args.after)
        if action == "study.export":
            raw = app.state.studies.export(pid, args.study_sha256)
            return {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
                "media_type": "application/json",
                "resource_uri": f"physicore://projects/{pid}/studies/{args.study_sha256}/export",
                "download_path": f"/api/drone/agent/exports/{pid}/{args.study_sha256}",
            }
        if action == "jobs.list":
            return app.state.jobs.page(pid, limit=args.limit, after=args.after)
        if action == "job.get":
            return operations.read_job(app, pid, args.job_id)
        if action == "job.cancel":
            return app.state.jobs.cancel(pid, args.job_id)
        if action == "job.retry":
            return app.state.jobs.retry(pid, args.job_id)
        raise ValueError("unimplemented action")
