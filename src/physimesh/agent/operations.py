"""Transport-free operations shared by legacy workbench routes and agent actions."""

from physimesh.drone.authoring import inspect_inputs
from physimesh.drone.capacity import hover_readiness
from physimesh.drone.models import project_from_mapping, readiness
from physimesh.projects.contracts import parse_snapshot
from physimesh.projects.performance import load_map, performance_refs


def inspect_project(app, project_id):
    project = app.state.projects.repository.get(project_id)
    snapshot = parse_snapshot(project["snapshot_json"])
    report = inspect_inputs(snapshot)
    ready = readiness(project_from_mapping(snapshot), "screening")
    sources, errors = {}, []
    for digest in performance_refs(snapshot):
        try:
            sources[digest] = load_map(app.state.projects.artifacts, digest)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    return {
        **report,
        "draft_version": project["draft_version"],
        "hover_readiness": hover_readiness(snapshot, sources, errors),
        "screening_readiness": {"ready": ready.ready, "blocking": ready.blocking},
    }


def freeze_project(app, project_id, expected_version, purpose, principal=None):
    kwargs = {}
    if app.state.settings.hosted_mode:
        kwargs = {
            "organization_id": app.state.identity.authorize(principal, project_id, write=True),
            "author_identity_id": principal.user_id,
        }
    return app.state.projects.freeze(project_id, expected_version, purpose, **kwargs)


def run_study(app, project_id, revision_sha256, principal=None):
    if app.state.settings.hosted_mode:
        app.state.projects.repository.revision(project_id, revision_sha256)
        return app.state.jobs.submit(
            project_id,
            "study",
            {
                "revision_sha256": revision_sha256,
                "model": app.state.studies.model_identity,
                "application_build": app.state.build.get("build_sha256"),
            },
            submitted_by=principal.user_id,
        )
    return app.state.studies.run(project_id, revision_sha256)


def compare_studies(app, project_id, before, after):
    return app.state.studies.compare(project_id, before, after)


def read_job(app, project_id, job_id):
    from physimesh.platform.worker import accept_publication

    retained = app.state.jobs.get(project_id, job_id)
    accept_publication(app, retained)
    return retained
