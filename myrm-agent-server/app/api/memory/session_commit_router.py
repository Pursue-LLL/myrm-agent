"""router (FastAPI APIRouter for Session Commit Two-Phase & Memory Diff Audit).

[POS]
app/api/memory/session_commit_router.py

[INPUT]
- app.schemas.session_commit, app.services.memory.session_commit_service

[OUTPUT]
- router (FastAPI APIRouter for Session Commit Two-Phase & Memory Diff Audit)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.session_commit import (
    CommitTaskStatusResponseDTO,
    MemoryDiffAuditResponseDTO,
    MemoryDiffItemDTO,
    SessionCommitRequest,
    SessionCommitResponseDTO,
)
from app.services.memory.session_commit_service import (
    SessionCommitService,
    get_session_commit_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/session-commit", tags=["Session Commit & Memory Diff Audit"])


@router.post(
    "/commit",
    response_model=SessionCommitResponseDTO,
    summary="Phase 1 synchronous session archival and Phase 2 gating",
)
async def commit_session(
    request: SessionCommitRequest,
    service: Annotated[SessionCommitService, Depends(get_session_commit_service)],
) -> SessionCommitResponseDTO:
    """Synchronously record messages.jsonl and gate asynchronous Phase 2 extraction."""
    return service.commit_session(request)


@router.post(
    "/execute-phase2/{task_id}",
    response_model=CommitTaskStatusResponseDTO,
    summary="Phase 2 asynchronous extraction, memory_diff generation, and .done marker",
)
async def execute_phase2(
    task_id: str,
    service: Annotated[SessionCommitService, Depends(get_session_commit_service)],
    simulated_diffs: list[MemoryDiffItemDTO] | None = None,
) -> CommitTaskStatusResponseDTO:
    """Execute Phase 2 memory extraction, emit memory_diff.json audit, and write .done marker."""
    try:
        return service.execute_phase2(task_id, simulated_diffs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/tasks/{task_id}",
    response_model=CommitTaskStatusResponseDTO,
    summary="Get status of an asynchronous commit task",
)
async def get_commit_task(
    task_id: str,
    service: Annotated[SessionCommitService, Depends(get_session_commit_service)],
) -> CommitTaskStatusResponseDTO:
    """Fetch live status of a two-phase session archival and extraction task."""
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Commit task '{task_id}' not found.")
    return task


@router.get(
    "/diff/{session_id}/{archive_id}",
    response_model=MemoryDiffAuditResponseDTO,
    summary="Fetch structured memory_diff.json audit for an archive bundle",
)
async def get_memory_diff(
    session_id: str,
    archive_id: str,
    service: Annotated[SessionCommitService, Depends(get_session_commit_service)],
) -> MemoryDiffAuditResponseDTO:
    """Retrieve full memory_diff.json audit recording all memory alterations."""
    diff = service.get_memory_diff(session_id, archive_id)
    if not diff:
        raise HTTPException(
            status_code=404,
            detail=f"memory_diff.json for session '{session_id}' archive '{archive_id}' not found.",
        )
    return diff


@router.get(
    "/archives/{session_id}",
    response_model=list[str],
    summary="List all sequential archive IDs for a session",
)
async def list_archives(
    session_id: str,
    service: Annotated[SessionCommitService, Depends(get_session_commit_service)],
) -> list[str]:
    """List sequential archive IDs (archive_001, archive_002, etc.) for a session."""
    return service.list_archives(session_id)
