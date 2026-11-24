"""Stateless fixed-wing screening; no aircraft approval or project mutation."""
import math
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from physimesh.drone.fixed_wing import screen_fixed_wing
from physimesh.drone.provenance import sha256_record

router = APIRouter(prefix="/api/drone/fixed-wing")


@router.get("/access")
def access() -> dict:
    """Confirm access through the application's existing bearer middleware."""
    return {"connected": True}


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


class CoefficientEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    mach_min: FiniteNumber
    mach_max: FiniteNumber
    reynolds_min: FiniteNumber
    reynolds_max: FiniteNumber
    lift_coefficient_min: FiniteNumber
    lift_coefficient_max: FiniteNumber


class FixedWingScreeningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    configuration: str
    evaluation: str
    density_kg_m3: FiniteNumber
    airspeed_m_s: FiniteNumber
    wing_area_m2: FiniteNumber
    span_m: FiniteNumber
    characteristic_length_m: FiniteNumber
    dynamic_viscosity_pa_s: FiniteNumber
    speed_of_sound_m_s: FiniteNumber
    lift_coefficient: FiniteNumber
    zero_lift_drag_coefficient: FiniteNumber
    span_efficiency: FiniteNumber
    coefficient_source: str = Field(min_length=1, max_length=2000)
    coefficient_envelope: CoefficientEnvelope

    @field_validator("coefficient_source")
    @classmethod
    def validate_coefficient_source(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Coefficient source must not be blank.")
        return value


@router.post("/screen")
def screen(body: FixedWingScreeningRequest) -> dict:
    inputs = body.model_dump(mode="json")
    component_result = screen_fixed_wing(inputs)
    result = {
        **component_result,
        "schema_version": "fixed_wing_screening_request_v1",
        "inputs": inputs,
        "input_sha256": sha256_record(inputs),
    }
    result["evaluation_sha256"] = sha256_record(result)
    return result
