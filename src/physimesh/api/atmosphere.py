"""Stateless reference-atmosphere evaluation; never aircraft approval."""
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from physimesh.drone.provenance import sha256_record
from physimesh.drone.standard_atmosphere import MODEL_ID, R_AIR, standard_atmosphere

router = APIRouter(prefix="/api/drone/atmosphere")


class AtmosphereRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    model_id: Literal[MODEL_ID]
    altitude_m: float = Field(ge=0, le=30000)
    altitude_kind: Literal["geometric", "geopotential"]


@router.post("/evaluate")
def evaluate(body: AtmosphereRequest) -> dict:
    """Reference values and input-bound evidence, no saved project mutation.

    To use these values in a project, explicitly save them through the existing
    draft/version/freeze flow. The evaluation cannot upgrade model applicability,
    measured-map domain, approval, evidence level or aircraft status.
    """
    inputs = body.model_dump(mode="json")
    state = standard_atmosphere(body.altitude_m, altitude_kind=body.altitude_kind)
    result = {
        "schema_version": "atmosphere_evaluation_v1",
        "inputs": inputs,
        "input_sha256": sha256_record(inputs),
        "model": {"model_id": MODEL_ID, "mesh_required": False,
                  "gas_constant_j_kg_k": R_AIR,
                  "sources": ["https://www.pdas.com/atmosdef.html",
                              "https://www.pdas.com/hydro.pdf"],
                  "scope": "standard dry reference atmosphere; not local weather"},
        "outputs": asdict(state),
        "atmosphere_values": {
            "source": f"{MODEL_ID}; {body.altitude_m} m {body.altitude_kind}",
            "altitude_m": body.altitude_m,
            "pressure_pa": state.pressure_pa,
            "temperature_k": state.temperature_k,
            "viscosity": {"law": "sutherland", "value_pa_s": None},
            "gamma": 1.4,
        },
        "evidence_level": "unverified",
        "aircraft_status": None,
        "interpretation": "Reference calculation only. No aircraft feasibility or validation is established.",
    }
    result["evaluation_sha256"] = sha256_record(result)
    return result
