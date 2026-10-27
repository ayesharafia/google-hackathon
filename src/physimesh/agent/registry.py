"""One catalog for browser, HTTP and MCP clients; no provider logic."""

from dataclasses import dataclass

from . import contracts as c


@dataclass(frozen=True)
class Action:
    id: str
    inputs: type[c.Strict]
    group: str
    effect: str
    description: str
    approval: bool = False
    hosted_only: bool = False

    def describe(self):
        return {
            "id": self.id,
            "version": 1,
            "tool_name": "physicore_" + self.id.replace(".", "_"),
            "description": self.description,
            "group": self.group,
            "effect": self.effect,
            "requires_approval": self.approval,
            "hosted_only": self.hosted_only,
            "input_schema": self.inputs.model_json_schema(),
            "output_schema": c.ActionResult.model_json_schema(),
        }


ACTIONS = {
    a.id: a
    for a in (
        Action(
            "projects.list", c.Empty, "read", "read", "List projects accessible in this credential scope."
        ),
        Action(
            "design.schema", c.Empty, "read", "read", "Discover supported edit fields, units and contracts."
        ),
        Action(
            "design.get",
            c.Project,
            "read",
            "read",
            "Read the saved draft and retained history; never unsaved browser inputs.",
        ),
        Action(
            "design.inspect",
            c.Project,
            "read",
            "read",
            "Inspect recorded saved inputs. Readiness is not physical qualification.",
        ),
        Action(
            "design.propose",
            c.Propose,
            "propose",
            "proposal",
            "Prepare explicit user-supplied edits with units; does not save the draft.",
        ),
        Action("proposal.get", c.Proposal, "read", "read", "Read the exact stored change proposal."),
        Action(
            "receipt.get",
            c.Receipt,
            "read",
            "read",
            "Read an exact recorded action receipt in this project and user scope.",
        ),
        Action(
            "proposal.apply",
            c.Proposal,
            "change",
            "draft_change",
            "Apply a reviewed proposal to its exact base version once.",
            True,
        ),
        Action(
            "proposal.undo",
            c.Proposal,
            "change",
            "draft_change",
            "Create a new draft restoring a proposal only if no later edits exist.",
            True,
        ),
        Action(
            "design.freeze",
            c.Freeze,
            "study",
            "revision",
            "Freeze the exact saved draft; engineering approval remains pending.",
            True,
        ),
        Action("revision.get", c.Revision, "read", "read", "Read a project-bound immutable revision."),
        Action(
            "study.run",
            c.Revision,
            "study",
            "study_admission",
            "Evaluate an existing eligible frozen design or admit its hosted job.",
            True,
        ),
        Action("study.get", c.Study, "read", "read", "Read exact retained study evidence."),
        Action("study.summary", c.Study, "read", "read", "Read recorded study summary and limitations."),
        Action(
            "study.compare",
            c.Compare,
            "read",
            "read",
            "Compare retained inputs/outcomes without inferring causation.",
        ),
        Action(
            "study.export",
            c.Study,
            "read",
            "read",
            "Get a permission-bound handle and checksum for exact retained JSON.",
        ),
        Action("jobs.list", c.Page, "read", "read", "Read a bounded page of hosted jobs.", hosted_only=True),
        Action(
            "job.get",
            c.Job,
            "read",
            "read_materialization",
            "Read attempts/status; may materialize an already accepted publication.",
            hosted_only=True,
        ),
        Action(
            "job.cancel",
            c.Job,
            "study",
            "job_recovery",
            "Explicitly request cancellation under existing job rules.",
            True,
            True,
        ),
        Action(
            "job.retry",
            c.Job,
            "study",
            "job_recovery",
            "Explicitly request another eligible attempt; no automatic retry.",
            True,
            True,
        ),
    )
}

PENDING = [
    "workspace_creation",
    "geometry",
    "source_library",
    "source_binding",
    "remaining_authoring",
    "reports",
    "collaboration",
    "owner_development",
    "http_mcp",
]


def get(action):
    if action not in ACTIONS:
        raise ValueError("unknown or unimplemented action")
    return ACTIONS[action]
