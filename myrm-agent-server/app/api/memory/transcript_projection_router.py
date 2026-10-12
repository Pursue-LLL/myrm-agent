"""SQLite transcript projection and adoption disambiguation API router.

[INPUT]
- TranscriptEntryDTO, SessionMessageDTO, BootstrapSessionRequestDTO, BootstrapSessionResponseDTO.
- TranscriptProjectionService singleton dependency.

[OUTPUT]
- APIRouter exposing endpoints for transcript appending, message ingestion, bootstrap projection, and message queries.

[POS]
- HTTP controller for Item 150 SqliteTranscriptProjectionSuite.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from app.schemas.transcript_projection import (
    BootstrapSessionRequestDTO,
    BootstrapSessionResponseDTO,
    SessionMessageDTO,
    TranscriptEntryDTO,
)
from app.services.memory.transcript_projection_service import (
    TranscriptProjectionService,
    get_transcript_projection_service,
)

router = APIRouter(prefix="/transcript-projection", tags=["Memory: Transcript Projection"])


@router.post(
    "/append",
    summary="Append raw transcript entries into the SQLite SSOT table",
)
def append_transcript_entries(
    entries: list[TranscriptEntryDTO],
    service: TranscriptProjectionService = Depends(get_transcript_projection_service),
) -> dict[str, int]:
    """Append a batch of raw transcript entries to the SQLite SSOT table."""
    count = service.append_transcript_entries(entries)
    return {"appended_count": count}


@router.post(
    "/ingest",
    summary="Ingest live host session messages into working memory",
)
def ingest_live_messages(
    messages: list[SessionMessageDTO],
    service: TranscriptProjectionService = Depends(get_transcript_projection_service),
) -> dict[str, int]:
    """Ingest a batch of live host messages before or during cold-start reconciliation."""
    count = service.ingest_live_messages(messages)
    return {"ingested_count": count}


@router.post(
    "/bootstrap",
    response_model=BootstrapSessionResponseDTO,
    summary="Execute idempotent cold-start bootstrap projection with adoption disambiguation",
)
def bootstrap_session(
    request: BootstrapSessionRequestDTO,
    service: TranscriptProjectionService = Depends(get_transcript_projection_service),
) -> BootstrapSessionResponseDTO:
    """Project SQLite transcript entries into working memory with duplicate created-time adoption."""
    return service.bootstrap_session(request)


@router.get(
    "/{session_id}/messages",
    response_model=list[SessionMessageDTO],
    summary="Get all projected session messages for a given session",
)
def get_session_messages(
    session_id: str = Path(..., description="Target session identifier"),
    service: TranscriptProjectionService = Depends(get_transcript_projection_service),
) -> list[SessionMessageDTO]:
    """Retrieve all working memory messages for the specified session in sequence order."""
    return service.get_session_messages(session_id)


@router.get(
    "/{session_id}/entries",
    response_model=list[TranscriptEntryDTO],
    summary="Get all raw transcript entries for a given session",
)
def get_transcript_entries(
    session_id: str = Path(..., description="Target session identifier"),
    service: TranscriptProjectionService = Depends(get_transcript_projection_service),
) -> list[TranscriptEntryDTO]:
    """Retrieve all raw transcript entries for the specified session in sequence order."""
    return service.get_transcript_entries(session_id)
