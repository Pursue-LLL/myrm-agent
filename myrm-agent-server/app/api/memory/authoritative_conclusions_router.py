"""FastAPI router for Explicit Authoritative Conclusions and Audit Tooling Suite (Item 111).

[POS]
app/api/memory/authoritative_conclusions_router.py

[INPUT]
- app.schemas.authoritative_conclusions, app.services.memory.authoritative_conclusions_service

[OUTPUT]
- router (FastAPI APIRouter for Explicit Authoritative Conclusions Suite)
"""


from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.authoritative_conclusions import (
    AuthoritativeConclusionDTO,
    ConclusionAnchorProjectionDTO,
    ConclusionAuditRecordDTO,
    DeleteConclusionRequest,
    DeprecateConclusionRequest,
    WriteConclusionRequest,
)
from app.services.memory.authoritative_conclusions_service import (
    AuthoritativeConclusionsService,
    get_authoritative_conclusions_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conclusions", tags=["Authoritative Conclusions"])


@router.post(
    "",
    response_model=AuthoritativeConclusionDTO,
    status_code=201,
    summary="Declare a new authoritative conclusion",
)
async def create_authoritative_conclusion(
    request: WriteConclusionRequest,
    service: Annotated[AuthoritativeConclusionsService, Depends(get_authoritative_conclusions_service)],
) -> AuthoritativeConclusionDTO:
    """Declare and persist an explicit authoritative normative decision."""
    return service.write_conclusion(request)


@router.get(
    "",
    response_model=list[AuthoritativeConclusionDTO],
    summary="List authoritative conclusions with filtering",
)
async def list_authoritative_conclusions(
    service: Annotated[AuthoritativeConclusionsService, Depends(get_authoritative_conclusions_service)],
    peer_id: str | None = Query(default=None, description="Optional peer ID filter"),
    status: str | None = Query(default=None, description="Optional status filter (proposed/confirmed/deprecated)"),
    scope_tag: str | None = Query(default=None, description="Optional scope category filter"),
    keyword: str | None = Query(default=None, description="Optional keyword search string"),
) -> list[AuthoritativeConclusionDTO]:
    """Retrieve conclusions matching filter criteria."""
    return service.list_conclusions(
        peer_id=peer_id,
        status_str=status,
        scope_tag=scope_tag,
        keyword=keyword,
    )


@router.get(
    "/anchor/projection",
    response_model=ConclusionAnchorProjectionDTO,
    summary="Retrieve anti-dilution prompt anchor projection",
)
async def get_anchor_projection(
    service: Annotated[AuthoritativeConclusionsService, Depends(get_authoritative_conclusions_service)],
) -> ConclusionAnchorProjectionDTO:
    """Render compact markdown block anchoring confirmed conclusions for system prompt injection."""
    return service.get_anchor_projection()


@router.get(
    "/{conclusion_id}",
    response_model=AuthoritativeConclusionDTO,
    summary="Get single authoritative conclusion by identifier",
)
async def get_conclusion(
    conclusion_id: str,
    service: Annotated[AuthoritativeConclusionsService, Depends(get_authoritative_conclusions_service)],
) -> AuthoritativeConclusionDTO:
    """Retrieve specific conclusion by unique ID."""
    conc = service.get_conclusion(conclusion_id)
    if conc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Authoritative conclusion not found: '{conclusion_id}'",
        )
    return conc


@router.put(
    "/{conclusion_id}/deprecate",
    response_model=AuthoritativeConclusionDTO,
    summary="Mark an authoritative conclusion as deprecated",
)
async def deprecate_conclusion(
    conclusion_id: str,
    request: DeprecateConclusionRequest,
    service: Annotated[AuthoritativeConclusionsService, Depends(get_authoritative_conclusions_service)],
) -> AuthoritativeConclusionDTO:
    """Transition conclusion status to deprecated and record audit log."""
    conc = service.deprecate_conclusion(conclusion_id, request)
    if conc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Authoritative conclusion not found: '{conclusion_id}'",
        )
    return conc


@router.delete(
    "/{conclusion_id}",
    status_code=204,
    summary="Physically erase an authoritative conclusion for PII/policy compliance",
)
async def delete_conclusion(
    conclusion_id: str,
    request: DeleteConclusionRequest,
    service: Annotated[AuthoritativeConclusionsService, Depends(get_authoritative_conclusions_service)],
) -> None:
    """Physically remove conclusion from active index while logging deletion audit event."""
    deleted = service.delete_conclusion(conclusion_id, request)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Authoritative conclusion not found: '{conclusion_id}'",
        )


@router.get(
    "/{conclusion_id}/audits",
    response_model=list[ConclusionAuditRecordDTO],
    summary="Retrieve audit ledger history for a conclusion",
)
async def get_conclusion_audits(
    conclusion_id: str,
    service: Annotated[AuthoritativeConclusionsService, Depends(get_authoritative_conclusions_service)],
) -> list[ConclusionAuditRecordDTO]:
    """Retrieve immutable audit history records for an authoritative conclusion."""
    return service.list_audits(conclusion_id)
