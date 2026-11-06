"""Stateless thermal screening; no approval or project mutation."""
import math
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from physimesh.drone.provenance import sha256_record
from physimesh.drone.thermal import screen_thermal

router = APIRouter(prefix="/api/drone/thermal")


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


class ThermalSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    duration_s: FiniteNumber
    ambient_temperature_k: FiniteNumber
    heat_input_w: FiniteNumber
    conductance_w_k: FiniteNumber


class ThermalScreeningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    evaluation: str
    mass_kg: FiniteNumber
    specific_heat_j_kg_k: FiniteNumber
    initial_temperature_k: FiniteNumber
    lumped_biot_number: FiniteNumber
    property_source: str = Field(min_length=1, max_length=2000)
    segments: list[ThermalSegment] = Field(min_length=1, max_length=128)

    @field_validator("property_source")
    @classmethod
    def validate_property_source(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Property source must not be blank.")
        return value


@router.post("/screen")
def screen(body: ThermalScreeningRequest) -> dict:
    inputs = body.model_dump(mode="json")
    component_result = screen_thermal(inputs)
    result = {
        **component_result,
        "schema_version": "thermal_screening_request_v1",
        "inputs": inputs,
        "input_sha256": sha256_record(inputs),
    }
    result["evaluation_sha256"] = sha256_record(result)
    return result
