# [POS]: app/api/memory/failure_search_router.py
# [INPUT]: app.schemas.failure_search, app.services.memory.failure_search_service
# [OUTPUT]: router (FastAPI APIRouter for Failure-Triggered Historical Session Retrieval Suite)

"""FastAPI router for Failure-Triggered Historical Session Retrieval Suite (Item 109)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.failure_search import (
    FailureRetrievalResultDTO,
    FailureTriggerConfigDTO,
    HistoricalResolutionEntryDTO,
    InterceptFailureRequest,
    InterceptFailureResponseDTO,
    RecordHistoricalResolutionRequest,
    SearchFailureRequest,
)
from app.services.memory.failure_search_service import (
    FailureSearchService,
    get_failure_search_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/failure-search", tags=["Failure Historical Session Retrieval"])


@router.post(
    "/query",
    response_model=FailureRetrievalResultDTO,
    summary="Search historical sessions for matching error resolutions and cautionary lessons",
)
async def query_failure_resolutions(
    request: SearchFailureRequest,
    service: Annotated[FailureSearchService, Depends(get_failure_search_service)],
) -> FailureRetrievalResultDTO:
    """Perform dual-track similarity search for historical fixes or cautionary failures."""
    return service.search_resolutions(request)


@router.post(
    "/resolutions",
    response_model=HistoricalResolutionEntryDTO,
    status_code=201,
    summary="Index a new historical resolution or cautionary dead end",
)
async def create_resolution_entry(
    request: RecordHistoricalResolutionRequest,
    service: Annotated[FailureSearchService, Depends(get_failure_search_service)],
) -> HistoricalResolutionEntryDTO:
    """Index an entry into the historical resolution repository."""
    return service.index_resolution(request)


@router.get(
    "/resolutions",
    response_model=list[HistoricalResolutionEntryDTO],
    summary="List all indexed historical resolution entries",
)
async def list_resolution_entries(
    service: Annotated[FailureSearchService, Depends(get_failure_search_service)],
) -> list[HistoricalResolutionEntryDTO]:
    """Retrieve all indexed historical error resolutions."""
    return service.list_resolutions()


@router.get(
    "/resolutions/{session_id}",
    response_model=HistoricalResolutionEntryDTO,
    summary="Directly read historical solution from session without guessing",
)
async def get_session_resolution(
    session_id: str,
    service: Annotated[FailureSearchService, Depends(get_failure_search_service)],
    turn_index: int | None = Query(default=None, description="Optional turn index in session"),
) -> HistoricalResolutionEntryDTO:
    """Read solution snippet directly associated with a specific session."""
    entry = service.get_resolution(session_id=session_id, turn_index=turn_index)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"No historical resolution entry found for session_id '{session_id}'",
        )
    return entry


@router.post(
    "/intercept",
    response_model=InterceptFailureResponseDTO,
    summary="Intercept tool failure and generate prompt injection block",
)
async def intercept_failure_event(
    request: InterceptFailureRequest,
    service: Annotated[FailureSearchService, Depends(get_failure_search_service)],
) -> InterceptFailureResponseDTO:
    """Intercept raw error and evaluate whether to inject historical resolution into LLM context."""
    return service.intercept_failure(request)


@router.get(
    "/config",
    response_model=FailureTriggerConfigDTO,
    summary="Get failure retrieval interception configuration",
)
async def get_configuration(
    service: Annotated[FailureSearchService, Depends(get_failure_search_service)],
) -> FailureTriggerConfigDTO:
    """Get active configuration for automated failure-triggered retrieval."""
    return service.get_config()


@router.put(
    "/config",
    response_model=FailureTriggerConfigDTO,
    summary="Update failure retrieval interception configuration",
)
async def update_configuration(
    request: FailureTriggerConfigDTO,
    service: Annotated[FailureSearchService, Depends(get_failure_search_service)],
) -> FailureTriggerConfigDTO:
    """Update active configuration parameters."""
    return service.update_config(request)
