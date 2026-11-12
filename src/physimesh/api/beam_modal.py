"""Dedicated strict stateless API for research-only uniform modal evaluation."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from physimesh.drone.beam_modal_request import beam_modal_catalog, evaluate_modal_beam
from physimesh.drone.provenance import sha256_record

from .beam_fem_variable import FiniteNumber, StrictInteger

router = APIRouter(prefix="/api/drone/beam-modal")


class ModalBeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    evaluation: str
    length_m: FiniteNumber
    E_pa: FiniteNumber
    I_m4: FiniteNumber
    mass_per_length_kg_m: FiniteNumber
    elements: StrictInteger
    modes: StrictInteger
    property_source: str = Field(min_length=1, max_length=2000)
    applicability_declaration: str = Field(min_length=1, max_length=2000)

    @field_validator("property_source", "applicability_declaration")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A nonblank declaration is required.")
        return value


@router.get("/catalog")
def catalog() -> dict:
    return beam_modal_catalog()


@router.post("/evaluate")
def evaluate(body: ModalBeamRequest) -> dict:
    inputs = body.model_dump(mode="json")
    result = {
        **evaluate_modal_beam(inputs), "inputs": inputs,
        "input_sha256": sha256_record(inputs),
    }
    result["evaluation_sha256"] = sha256_record(result)
    return result
