"""Strict stateless API for experimental variable-inertia beam evaluation."""

import math
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from physimesh.drone.beam_fem_variable_request import evaluate_variable_beam
from physimesh.drone.provenance import sha256_record

router = APIRouter(prefix="/api/drone/beam-fem-variable")


def _finite(value):
    if type(value) not in (int, float):
        raise ValueError("A finite builtin number is required.")
    if type(value) is int and value.bit_length() > 1024:
        raise ValueError("Number is out of range.")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        raise ValueError("Number is out of range.") from None
    if not finite:
        raise ValueError("A finite builtin number is required.")
    return value


def _integer(value):
    if type(value) is not int:
        raise ValueError("A builtin integer is required.")
    return _finite(value)


def _list(value):
    if type(value) is not list:
        raise ValueError("A builtin list is required.")
    return value


FiniteNumber = Annotated[int | float, BeforeValidator(_finite)]
StrictInteger = Annotated[int, BeforeValidator(_integer)]
NumberList = Annotated[
    list[FiniteNumber], Field(min_length=2, max_length=65), BeforeValidator(_list)
]


class Probe(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    element_index: StrictInteger
    local_coordinate: Annotated[FiniteNumber, Field(ge=0, le=1)]


class VariableBeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    evaluation: str
    length_m: FiniteNumber
    E_pa: FiniteNumber
    second_moments_m4: NumberList
    nodes_m: NumberList
    outer_fibre_m: FiniteNumber
    tip_force_n: FiniteNumber
    uniform_load_n_m: FiniteNumber
    ramp_load_root_n_m: FiniteNumber
    ramp_load_tip_n_m: FiniteNumber
    tip_moment_n_m: FiniteNumber
    probes: Annotated[list[Probe], Field(min_length=1, max_length=128), BeforeValidator(_list)]
    property_source: str = Field(min_length=1, max_length=2000)
    applicability_declaration: str = Field(min_length=1, max_length=2000)

    @field_validator("property_source", "applicability_declaration")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A nonblank declaration is required.")
        return value


@router.post("/evaluate")
def evaluate(body: VariableBeamRequest) -> dict:
    inputs = body.model_dump(mode="json")
    result = {
        **evaluate_variable_beam(inputs),
        "schema_version": "variable_beam_request_v1",
        "inputs": inputs,
        "input_sha256": sha256_record(inputs),
    }
    result["evaluation_sha256"] = sha256_record(result)
    return result
