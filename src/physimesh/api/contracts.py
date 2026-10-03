"""Read-only schema discovery; this endpoint does not approve designs or results."""
from fastapi import APIRouter, HTTPException

from physimesh.projects.serialization import CONTRACTS

router = APIRouter(prefix='/api/drone/contracts')


@router.get('')
def versions():
    return {'versions': sorted(CONTRACTS), 'qualification': 'Schema consistency is not authenticated approval or validation.'}


@router.get('/{version}')
def schema(version: str):
    model = CONTRACTS.get(version)
    if model is None:
        raise HTTPException(404, 'unknown contract version')
    return model.model_json_schema()
