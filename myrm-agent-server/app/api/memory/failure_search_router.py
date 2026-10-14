"""FastAPI router for Failure-Triggered Historical Session Retrieval Suite (Item 109).

[POS]
app/api/memory/failure_search_router.py

[INPUT]
- app.schemas.failure_search, app.services.memory.failure_search_service

[OUTPUT]
- router (FastAPI APIRouter for Failure-Triggered Historical Session Retrieval Suite)
"""


from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.failure_search import (
    FailureRetrievalResultDTO,
    FailureTriggerConfigDTO,
    HistoricalResolutionEntryDTO,
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
