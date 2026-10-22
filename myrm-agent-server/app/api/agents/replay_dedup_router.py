"""FastAPI router for Multi-Agent Tool Replay History Deduplication & Status Harmonization (Item 57).

[INPUT]
- app.schemas.replay_dedup::{
    MergeReplayHistoryRequest,
    SyncSubagentStatusRequest,
    HeartbeatLeaseCheckRequest,
  }
- app.services.agent.replay_dedup_service::{
    ReplayDedupService,
    get_replay_dedup_service,
  }

[OUTPUT]
- REST endpoints under /agents/replay-dedup for compacting consecutive read-only tool history,
  harmonizing subagent status transitions, and preventing UI deadlocks.

[POS]
- HTTP API layer for Item 57 multi-agent tool replay deduplication and status machine synchronization.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from app.schemas.replay_dedup import (
    HeartbeatLeaseCheckRequest,
    MergeReplayHistoryRequest,
    SyncSubagentStatusRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.replay_dedup_service import (
    ReplayDedupService,
    get_replay_dedup_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/replay-dedup", tags=["Subagent Replay Deduplication & Harmonization"])


@router.post(
    "/merge-history",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Compact and deduplicate consecutive read-only tool invocations",
)
async def merge_replay_history(
    req: MergeReplayHistoryRequest,
    service: ReplayDedupService = Depends(get_replay_dedup_service),
) -> StandardSuccessResponse:
    """Consolidate repeated idempotent tool operations to conserve replay context tokens."""
    result = service.merge_replay_history(req)
    return create_success_response(data=result.model_dump())


@router.post(
    "/status-sync",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Synchronize and transition subagent execution status machine",
)
async def sync_subagent_status(
    req: SyncSubagentStatusRequest,
    service: ReplayDedupService = Depends(get_replay_dedup_service),
) -> StandardSuccessResponse:
    """Transition subagent status adhering strictly to monotonic state machine rules."""
    result = service.sync_subagent_status(req)
    return create_success_response(data=result.model_dump())


@router.post(
    "/watchdog-check",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Scan active subagents and terminate expired leases to prevent deadlocks",
)
async def check_watchdog_leases(
    req: HeartbeatLeaseCheckRequest,
    service: ReplayDedupService = Depends(get_replay_dedup_service),
) -> StandardSuccessResponse:
    """Scan and auto-terminate hung subagent leases to prevent UI status deadlocks."""
    result = service.check_watchdog_leases(req.session_id)
    return create_success_response(data=result.model_dump())


@router.get(
    "/{session_id}/statuses",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve current status snapshot of all subagents in a session",
)
async def get_subagent_statuses(
    session_id: str,
    service: ReplayDedupService = Depends(get_replay_dedup_service),
) -> StandardSuccessResponse:
    """Fetch status mapping of all subagents tracked within the given session."""
    statuses = service.get_subagent_statuses(session_id)
    return create_success_response(data={"session_id": session_id, "statuses": statuses})
