"""Explicit action inputs; unknown fields and nonfinite quantities are refused."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ID = Annotated[str, Field(pattern=r"^project_[a-f0-9]{32}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
RequestID = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Empty(Strict):
    pass


class Project(Strict):
    project_id: ID


class Edit(Strict):
    field: Literal["mission.payload_mass_kg", "mission.duration_s", "mass_kg", "cg_body_m"]
    item_name: str | None = Field(default=None, min_length=1, max_length=160)
    value: float | list[float]
    unit: Literal["kg", "g", "s", "min", "m", "cm", "mm"]


class Propose(Project):
    expected_version: int = Field(ge=0)
    edits: list[Edit] = Field(min_length=1, max_length=25)


class Proposal(Project):
    proposal_id: str = Field(pattern=r"^proposal_[a-f0-9]{32}$")


class Freeze(Project):
    expected_version: int = Field(ge=0)
    purpose: Literal["screening", "feasibility", "cfd_run"] = "screening"


class Revision(Project):
    revision_sha256: Digest


class Study(Project):
    study_sha256: Digest


class Compare(Project):
    before: Digest
    after: Digest


class Job(Project):
    job_id: str = Field(pattern=r"^job_[a-f0-9]{32}$")


class Receipt(Project):
    receipt_id: str = Field(pattern=r"^receipt_[a-f0-9]{32}$")


class Page(Project):
    after: str = Field(default="", max_length=1000)
    limit: int = Field(default=25, ge=1, le=25)


class Call(Strict):
    request_id: RequestID
    arguments: dict


class GrantInput(Project):
    name: str = Field(min_length=1, max_length=100)
    groups: list[Literal["read", "propose", "change", "study"]] = Field(
        default_factory=lambda: ["read", "propose"], min_length=1, max_length=4
    )
    lifetime_s: int = Field(default=3600, ge=60, le=86400)
    max_calls: int = Field(default=200, ge=1, le=1000)

    @model_validator(mode="after")
    def unique_groups(self):
        if len(self.groups) != len(set(self.groups)):
            raise ValueError("duplicate capability group")
        return self


class Confirm(Strict):
    execute: bool = True


class ActionResult(Strict):
    schema_version: Literal["physicore_action_result_v1"] = "physicore_action_result_v1"
    action: str
    request_id: str
    receipt_id: str | None
    project_id: str | None
    status: Literal["completed", "queued", "awaiting_review", "uncertain", "running", "failed"]
    data: dict
