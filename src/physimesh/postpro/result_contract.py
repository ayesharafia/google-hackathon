"""Single results_v1 envelope for API, presentation and export; no status upgrades."""
from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


def _finite_tree(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('results cannot contain NaN or infinity')
    if isinstance(value, dict):
        for child in value.values():
            _finite_tree(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            _finite_tree(child)


class Provenance(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_group_sha256: Digest
    code_version: str
    image_digest: Annotated[str, Field(pattern=r'^[^\s@]+@sha256:[0-9a-f]{64}$')]


class ResultsV1(BaseModel):
    """Numerical success and independent evidence are separate explicit fields.

    Metric dictionaries preserve recipes and native comparison detail without
    inventing unavailable data. Recursively reject all nonfinite values.
    """
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['results_v1']
    run_group_id: Annotated[str, Field(pattern=r'^[0-9a-f]{16}$')]
    label: str
    status: Literal['numerical_checks_passed', 'diagnostic_only']
    evidence: Literal['unverified']
    independent_review: Literal['pending']
    provenance: Provenance
    case: dict[str, JsonValue]
    runs: Annotated[list[dict[str, JsonValue]], Field(min_length=3, max_length=3)]
    mesh_study: dict[str, JsonValue]
    plots: list[dict[str, JsonValue]]
    interpretation: list[dict[str, JsonValue]]
    refusals: list[dict[str, JsonValue]]
    limitations: list[str]

    @model_validator(mode='after')
    def semantics(self):
        _finite_tree(self.model_dump())
        if [run.get('level') for run in self.runs] != ['coarse', 'medium', 'fine']:
            raise ValueError('results need ordered coarse, medium, fine sphere evidence')
        if 'VERIFICATION CASE' not in self.label:
            raise ValueError('sphere results require verification label')
        accepted = True
        for run in self.runs:
            if not isinstance(run.get('cd'), (int, float)) or isinstance(run['cd'], bool):
                raise ValueError('each sphere result requires numeric Cd')  # noqa: TRY004 - Pydantic wraps ValueError
            reconciliation = run.get('reconciliation', {})
            convergence = run.get('convergence', {})
            if not isinstance(reconciliation, dict) or not isinstance(convergence, dict):
                raise ValueError('each run requires reconciliation and convergence')  # noqa: TRY004 - validation error
            if reconciliation.get('status') not in ('accepted', 'diagnostic_only'):
                raise ValueError('missing reconciliation status')
            if type(convergence.get('passed')) is not bool:
                raise ValueError('missing convergence gate')
            accepted &= reconciliation['status'] == 'accepted' and convergence['passed']
        if self.status == 'numerical_checks_passed' and not accepted:
            raise ValueError('cannot upgrade failed numerical gates')
        return self


def assemble_results(group: dict, loads: dict, plots: list[dict], *,
                     interpretation: list[dict] | None = None, refusals: list[dict] | None = None) -> dict:
    """Retain the numerical statuses; independent review remains pending."""
    passed = all(run['reconciliation']['status'] == 'accepted' and run['convergence']['passed']
                 for run in loads['runs'])
    record = ResultsV1(
        schema_version='results_v1', run_group_id=loads['run_group_sha256'][:16],
        label=group['label'], status='numerical_checks_passed' if passed else 'diagnostic_only',
        evidence='unverified', independent_review='pending',
        provenance=Provenance(run_group_sha256=loads['run_group_sha256'], code_version=group['code_version'],
                              image_digest=group['image_digest']),
        case={key: group[key] for key in ('Re', 'D_m', 'rho_ref_kg_m3', 'nu_m2_s', 'u_inf_m_s')},
        runs=loads['runs'], mesh_study=loads['mesh_study'], plots=plots,
        interpretation=interpretation or [], refusals=refusals or [],
        limitations=['Sphere verification case; no aircraft capacity or validation claim.',
                     'Independent physics review pending; evidence remains unverified.',
                     'Mesh GCI excludes domain, boundary, model and geometric errors; asymptotic range not demonstrated.',
                     'Slice interpolation and in-plane streamlines are visualization only.'],
    )
    return record.model_dump(mode='json')
