"""Stateless experimental isolated-hover BEMT; physical validation is not established."""
import math
from typing import Annotated

from fastapi import APIRouter
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
)

from physimesh.drone.hover_bemt_request import evaluate_hover_bemt
from physimesh.drone.provenance import sha256_record

router = APIRouter(prefix="/api/drone/hover-bemt")


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


def _validate_strict_finite_integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("A finite integer is required.")
    if value.bit_length() > 1024:
        raise ValueError("Integer is too large.")
    try:
        finite = math.isfinite(float(value))
    except OverflowError:
        raise ValueError("Integer is out of range.") from None
    if not finite:
        raise ValueError("A finite integer is required.")
    return value


StrictFiniteInteger = Annotated[
    StrictInt, BeforeValidator(_validate_strict_finite_integer)
]


class HoverBEMTRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    evaluation: str
    radius_m: FiniteNumber
    angular_speed_rad_s: FiniteNumber
    density_kg_m3: FiniteNumber
    blade_count: StrictFiniteInteger
    chord_m: FiniteNumber
    lift_curve_slope_per_rad: FiniteNumber
    profile_drag_coefficient: FiniteNumber
    pitch_tip_rad: FiniteNumber
    root_cutout_fraction: FiniteNumber
    twist_law: str
    annuli: StrictFiniteInteger
    pitch_root_rad: FiniteNumber | None
    property_source: str = Field(min_length=1, max_length=2000)
    applicability_declaration: str = Field(min_length=1, max_length=2000)

    @field_validator("property_source", "applicability_declaration")
    @classmethod
    def validate_nonblank_declaration(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Source and applicability declarations must not be blank.")
        return value


@router.post("/evaluate")
def evaluate(body: HoverBEMTRequest) -> dict:
    inputs = body.model_dump(mode="json")
    component_result = evaluate_hover_bemt(inputs)
    result = {
        **component_result,
        "schema_version": "hover_bemt_request_v1",
        "inputs": inputs,
        "input_sha256": sha256_record(inputs),
    }
    result["evaluation_sha256"] = sha256_record(result)
    return result
