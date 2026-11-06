"""Stateless registry evaluation; no aircraft approval or project mutation."""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from physimesh.drone.evaluation import evaluate_request, model_catalog
from physimesh.drone.provenance import sha256_record

router = APIRouter(prefix="/api/drone/evaluations")

OutputName = Literal["pressure_pa", "temperature_k", "density_kg_m3"]
_OUTPUT_UNITS = {
    "pressure_pa": "Pa",
    "temperature_k": "K",
    "density_kg_m3": "kg/m^3",
}


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    configuration: str
    evaluation: str
    altitude_m: int | float = Field(ge=0, le=30000)
    altitude_kind: Literal["geometric", "geopotential"]
    outputs: list[OutputName] = Field(
        default_factory=lambda: list(_OUTPUT_UNITS), min_length=1
    )

    @field_validator("altitude_m", mode="before")
    @classmethod
    def validate_altitude(cls, value: object) -> int | float:
        if type(value) not in (int, float) or not 0 <= value <= 30000:
            raise ValueError("Invalid evaluation request.")
        return value

    @field_validator("outputs")
    @classmethod
    def validate_outputs(cls, value: list[OutputName]) -> list[OutputName]:
        if len(value) != len(set(value)):
            raise ValueError("Invalid evaluation request.")
        return value


@router.get("/catalog")
def catalog() -> dict:
    return model_catalog()


@router.post("/evaluate")
def evaluate(body: EvaluationRequest) -> dict:
    inputs = body.model_dump(mode="json", exclude_unset=True)
    component_result = evaluate_request(inputs)
    output_units = (
        {name: _OUTPUT_UNITS[name] for name in component_result["outputs"]}
        if component_result["status"] == "REFERENCE_COMPUTED"
        else {}
    )
    result = {
        **component_result,
        "schema_version": "evaluation_request_v1",
        "inputs": inputs,
        "input_sha256": sha256_record(inputs),
        "output_units": output_units,
        "evidence_level": "unverified",
        "aircraft_status": None,
    }
    result["evaluation_sha256"] = sha256_record(result)
    return result
