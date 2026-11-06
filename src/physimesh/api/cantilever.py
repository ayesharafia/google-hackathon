"""Stateless cantilever screening; no approval or project mutation."""
import math
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from physimesh.drone.cantilever import screen_cantilever
from physimesh.drone.provenance import sha256_record

router = APIRouter(prefix="/api/drone/cantilever")


def _validate_finite_number(value: object) -> int | float:
    if type(value) not in (int, float):
        raise ValueError("A finite number is required.")
    if type(value) is int and value.bit_length() > 1024:
        raise ValueError("Integer is too large.")
    try:
        converted = float(value)
    except OverflowError:
        raise ValueError("Number is out of range.") from None
    if not math.isfinite(converted):
        raise ValueError("A finite number is required.")
    return value


FiniteNumber = Annotated[int | float, BeforeValidator(_validate_finite_number)]


class CantileverScreeningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    evaluation: str
    length_m: FiniteNumber
    width_m: FiniteNumber
    depth_m: FiniteNumber
    youngs_modulus_pa: FiniteNumber
    tip_load_n: FiniteNumber
    uniform_load_n_m: FiniteNumber
    property_source: str = Field(min_length=1, max_length=2000)
    applicability_declaration: str = Field(min_length=1, max_length=2000)
    declared_min_slenderness: FiniteNumber
    declared_max_deflection_ratio: FiniteNumber
    declared_max_slope_rad: FiniteNumber

    @field_validator("property_source", "applicability_declaration")
    @classmethod
    def validate_nonblank_declaration(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Source and applicability declarations must not be blank.")
        return value


@router.post("/screen")
def screen(body: CantileverScreeningRequest) -> dict:
    inputs = body.model_dump(mode="json")
    component_result = screen_cantilever(inputs)
    result = {
        **component_result,
        "schema_version": "cantilever_screening_request_v1",
        "inputs": inputs,
        "input_sha256": sha256_record(inputs),
    }
    result["evaluation_sha256"] = sha256_record(result)
    return result
