# [POS]: app/api/memory/procedure_experience_router.py
# [INPUT]: app.schemas.procedure_experience, app.services.memory.procedure_experience_service
# [OUTPUT]: router (FastAPI APIRouter for Procedure Experience & Dual-Node Retrieval)

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import ProcedureMemoryEntry

from app.schemas.procedure_experience import (
    DualNodeRetrievalRequest,
    DualNodeRetrievalResponseDTO,
    MultiIntentSplitRequest,
    MultiIntentSplitResponseDTO,
    ProcedureMemoryEntryDTO,
    ProtocolValidationResponseDTO,
    RegisterProcedureMemoryRequest,
)
from app.services.memory.procedure_experience_service import (
    ProcedureExperienceService,
    get_procedure_experience_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/procedure", tags=["Procedure Experience & Dual-Node Retrieval"])


@router.post(
    "/register",
    response_model=ProcedureMemoryEntryDTO,
    summary="Register an 8-field procedure-shaped experience memory",
)
async def register_procedure(
    request: RegisterProcedureMemoryRequest,
    service: Annotated[ProcedureExperienceService, Depends(get_procedure_experience_service)],
) -> ProcedureMemoryEntryDTO:
    """Register a new procedure memory adhering to the 8-field structured protocol."""
    try:
        return service.register_entry(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/retrieve",
    response_model=DualNodeRetrievalResponseDTO,
    summary="Execute fixed-count dual-node retrieval",
)
async def retrieve_dual_node(
    request: DualNodeRetrievalRequest,
    service: Annotated[ProcedureExperienceService, Depends(get_procedure_experience_service)],
) -> DualNodeRetrievalResponseDTO:
    """Execute fixed-count retrieval at either 'first_user' intent or 'pre_write' intercept nodes."""
    return service.retrieve(request)


@router.post(
    "/validate",
    response_model=ProtocolValidationResponseDTO,
    summary="Validate 8-field protocol conformance",
)
async def validate_protocol(
    request: RegisterProcedureMemoryRequest,
    service: Annotated[ProcedureExperienceService, Depends(get_procedure_experience_service)],
) -> ProtocolValidationResponseDTO:
    """Check whether a candidate memory entry conforms to the 8-field procedure protocol."""
    domain_entry = ProcedureMemoryEntry(
        entry_id=request.entry_id or "temp_check",
        name=request.name,
        retrieval_anchor=request.retrieval_anchor or "",
        operation_intent=request.operation_intent,
        preconditions=list(request.preconditions),
        immutable_boundary=list(request.immutable_boundary),
        procedure_steps=list(request.procedure_steps),
        write_field_provenance=dict(request.write_field_provenance),
        anti_patterns=list(request.anti_patterns),
        applicability=list(request.applicability),
        negative_applicability=list(request.negative_applicability),
    )
    return service.validate_protocol(domain_entry)


@router.post(
    "/split-intents",
    response_model=MultiIntentSplitResponseDTO,
    summary="Decompose multi-intent traces into distinct fragments",
)
async def split_intents(
    request: MultiIntentSplitRequest,
    service: Annotated[ProcedureExperienceService, Depends(get_procedure_experience_service)],
) -> MultiIntentSplitResponseDTO:
    """Split raw multi-intent execution trace into single-intent procedure chunks."""
    return service.split_intents(request.raw_text)


@router.get(
    "/list",
    response_model=list[ProcedureMemoryEntryDTO],
    summary="List all registered procedure memories",
)
async def list_procedures(
    service: Annotated[ProcedureExperienceService, Depends(get_procedure_experience_service)],
) -> list[ProcedureMemoryEntryDTO]:
    """Retrieve all indexed procedure-shaped memory entries."""
    return service.list_entries()


@router.get(
    "/{entry_id}",
    response_model=ProcedureMemoryEntryDTO,
    summary="Get single procedure memory by ID",
)
async def get_procedure(
    entry_id: str,
    service: Annotated[ProcedureExperienceService, Depends(get_procedure_experience_service)],
) -> ProcedureMemoryEntryDTO:
    """Fetch an individual procedure-shaped memory entry."""
    entry = service.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Procedure entry '{entry_id}' not found.")
    return entry
