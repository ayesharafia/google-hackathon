"""Stateless dependency planning without execution authority."""
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from physimesh.drone.dependency_plan import dependency_plan
from physimesh.drone.provenance import sha256_record

router = APIRouter(prefix="/api/drone/dependencies")

Text = Annotated[str, Field(min_length=1, max_length=80)]
LIMITATIONS = (
    "declaration_metadata_only",
    "no_execution",
    "no_physical_validation",
    "no_backend_availability_verification",
    "no_adequacy_or_cost_selection",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Port(StrictModel):
    name: Text
    unit: Text
    frame: Text


class DependencyModel(StrictModel):
    id: Text
    inputs: list[Port] = Field(max_length=128)
    outputs: list[Port] = Field(max_length=128)


class Connection(StrictModel):
    from_model: Text
    from_port: Text
    to_model: Text
    to_port: Text


class Target(StrictModel):
    model: Text
    port: Text


class Graph(StrictModel):
    models: list[DependencyModel] = Field(max_length=128)
    connections: list[Connection] = Field(max_length=4096)


class DependencyPlanRequest(StrictModel):
    graph: Graph
    targets: list[Target] = Field(min_length=1, max_length=128)


@router.post("/plan")
def plan(body: DependencyPlanRequest) -> dict:
    inputs = body.model_dump(mode="json")
    component_result = dependency_plan(inputs["graph"], inputs["targets"])
    result = {
        **component_result,
        "schema_version": "dependency_plan_request_v1",
        "inputs": inputs,
        "input_sha256": sha256_record(inputs),
        "limitations": list(LIMITATIONS),
    }
    result["evaluation_sha256"] = sha256_record(result)
    return result
