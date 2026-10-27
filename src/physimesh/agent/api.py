"""Authenticated agent gateway and separate trusted human control endpoints."""

import re
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from physimesh.api.projects import operation
from physimesh.api.sessions import same_origin
from physimesh.platform.identity import Denied
from physimesh.platform.scoped_artifacts import artifact_scope

from .contracts import Call, Confirm, GrantInput, Project, Study
from .store import encoded

router = APIRouter(prefix="/api/drone/agent")


def service(request):
    return request.app.state.agent


def trusted(request, *, changing=False):
    ctx = service(request).context(request)
    if ctx.grant_id:
        raise Denied("AI-client grants cannot manage connections or confirm/reject human reviews.")
    if changing and not same_origin(request):
        raise Denied("Confirm changes from this workspace page.")
    return ctx


@router.get("/catalog")
def catalog(request: Request, project_id: str | None = None):
    if project_id:
        project_id = operation(lambda: Project(project_id=project_id).project_id)
    return operation(lambda: service(request).catalog(service(request).context(request), project_id))


@router.post("/actions/{action}")
def call(request: Request, action: str, body: Call):
    return operation(lambda: service(request).call(service(request).context(request), action, body))


@router.post("/grants", status_code=201)
def mint(request: Request, body: GrantInput):
    return operation(lambda: service(request).policy.mint(trusted(request, changing=True), body))


@router.get("/grants")
def grants(request: Request):
    return operation(lambda: service(request).policy.grants(trusted(request)))


@router.delete("/grants/{grant_id}")
def revoke(request: Request, grant_id: str):
    return service(request).policy.revoke(trusted(request, changing=True), grant_id)


@router.get("/records/{project_id}")
def records(request: Request, project_id: str):
    operation(lambda: Project(project_id=project_id))
    return operation(lambda: service(request).records(service(request).context(request), project_id))


@router.post("/reviews/{review_id}/confirm")
def confirm(request: Request, review_id: str, body: Confirm):
    return operation(
        lambda: service(request).confirm(trusted(request, changing=True), review_id, body.execute)
    )


@router.post("/reviews/{review_id}/reject")
def reject(request: Request, review_id: str):
    agent = service(request)
    ctx = trusted(request, changing=True)
    with agent.store.database.connection(write=True) as db:
        agent.store.lock(db)
        row = db.execute(
            "SELECT project_id FROM agent_reviews WHERE review_id=? AND actor=?", (review_id, ctx.actor)
        ).fetchone()
        if row:
            agent.policy.check_locked(db, ctx, row["project_id"], write=True)
            db.execute(
                "UPDATE agent_reviews SET status='rejected' WHERE review_id=? AND status IN ('pending','approved')",
                (review_id,),
            )
    return {"review_id": review_id, "status": "rejected"}


@router.get("/exports/{project_id}/{study_sha256}")
def export(request: Request, project_id: str, study_sha256: str):
    args = operation(lambda: Study(project_id=project_id, study_sha256=study_sha256))
    agent = service(request)
    ctx = agent.context(request)
    operation(
        lambda: agent.call(ctx, "study.export", Call(request_id=uuid4().hex, arguments=args.model_dump()))
    )
    with artifact_scope(project_id):
        raw = operation(lambda: request.app.state.studies.export(project_id, study_sha256))
    return Response(
        raw,
        media_type="application/json",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": "attachment; filename=retained-study.json",
        },
    )


@router.get("/resources")
def resources(request: Request):
    agent = service(request)
    ctx = agent.policy.refresh(agent.context(request))
    items = [
        {"uri": "physicore://capabilities", "name": "Action capabilities", "mimeType": "application/json"},
        {
            "uri": "physicore://design-schema",
            "name": "Editable fields and units",
            "mimeType": "application/json",
        },
    ]
    if ctx.project_id:
        pid = ctx.project_id
        agent.policy.authorize(ctx, pid)
        items.extend(
            {"uri": f"physicore://projects/{pid}/{suffix}", "name": name, "mimeType": "application/json"}
            for suffix, name in [("draft", "Saved draft"), ("inspection", "Saved input checks")]
        )
        project = request.app.state.projects.repository.get(pid)
        items.extend(
            {
                "uri": f"physicore://projects/{pid}/studies/{s['study_sha256']}",
                "name": "Retained study " + s["study_sha256"][:12],
                "mimeType": "application/json",
            }
            for s in project["studies"][:25]
        )
    return {"resources": items}


@router.get("/resource")
def resource(request: Request, uri: str = Query(max_length=500)):
    agent = service(request)
    ctx = agent.context(request)
    if uri == "physicore://capabilities":
        value = agent.catalog(ctx)
    else:
        if uri == "physicore://design-schema":
            action, args = "design.schema", {}
        else:
            match = re.fullmatch(
                r"physicore://projects/(project_[a-f0-9]{32})/(draft|inspection|studies/[a-f0-9]{64}(?:/export)?|revisions/[a-f0-9]{64})",
                uri,
            )
            if not match:
                raise Denied("Unknown or unsupported resource URI.")
            pid, path = match.groups()
            args = {"project_id": pid}
            if path in ("draft", "inspection"):
                action = "design.get" if path == "draft" else "design.inspect"
            elif path.startswith("revisions/"):
                action = "revision.get"
                args["revision_sha256"] = path.split("/")[1]
            else:
                action = "study.get"
                args["study_sha256"] = path.split("/")[1]
            if path.endswith("/export"):
                operation(
                    lambda: agent.call(ctx, "study.export", Call(request_id=uuid4().hex, arguments=args))
                )
                with artifact_scope(pid):
                    raw = operation(lambda: request.app.state.studies.export(pid, args["study_sha256"]))
                if len(raw) > 250000:
                    from fastapi import HTTPException

                    raise HTTPException(
                        422, "Resource exceeds inline budget; use the authorized download handle."
                    )
                value = {"exact_utf8_json": raw.decode("utf-8")}
                return {"uri": uri, "mime_type": "application/json", "text": encoded(value)}
        value = operation(lambda: agent.call(ctx, action, Call(request_id=uuid4().hex, arguments=args)))
    return {"uri": uri, "mime_type": "application/json", "text": encoded(value)}
