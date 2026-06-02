"""
[INPUT]
- app.core.commitment.sqlite_store::SqlAlchemyCommitmentStore
- myrm_agent_harness.toolkits.commitment.types::{CommitmentStatus, CommitmentRecord}

[OUTPUT]
- router: Commitment REST endpoints (list/dismiss/snooze)

[POS]
Commitment tracking REST API. Provides endpoints for listing, dismissing,
and snoozing commitments extracted from conversations.
"""

import logging
import time

from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.toolkits.commitment.types import CommitmentStatus
from pydantic import BaseModel, Field

from app.core.commitment.sqlite_store import SqlAlchemyCommitmentStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/commitments", tags=["Commitments"])

_store = SqlAlchemyCommitmentStore()


class CommitmentResponse(BaseModel):
    id: str
    agent_id: str
    user_id: str
    channel: str
    kind: str
    sensitivity: str
    status: str
    reason: str
    suggested_text: str
    dedupe_key: str
    confidence: float
    due_earliest_ms: int
    due_latest_ms: int
    due_timezone: str
    source_chat_id: str | None
    attempts: int
    created_at: str
    snoozed_until_ms: int | None


class SnoozeRequest(BaseModel):
    until_ms: int = Field(description="Epoch ms to snooze until")


class CommitmentListResponse(BaseModel):
    items: list[CommitmentResponse]
    total: int


def _to_response(r: object) -> CommitmentResponse:
    from myrm_agent_harness.toolkits.commitment.types import CommitmentRecord

    assert isinstance(r, CommitmentRecord)
    return CommitmentResponse(
        id=r.id,
        agent_id=r.agent_id,
        user_id=r.user_id,
        channel=r.channel,
        kind=r.kind.value,
        sensitivity=r.sensitivity.value,
        status=r.status.value,
        reason=r.reason,
        suggested_text=r.suggested_text,
        dedupe_key=r.dedupe_key,
        confidence=r.confidence,
        due_earliest_ms=r.due_window.earliest_ms,
        due_latest_ms=r.due_window.latest_ms,
        due_timezone=r.due_window.timezone,
        source_chat_id=r.source_chat_id,
        attempts=r.attempts,
        created_at=r.created_at.isoformat(),
        snoozed_until_ms=r.snoozed_until_ms,
    )


@router.get("", response_model=CommitmentListResponse)
async def list_commitments(
    status: str | None = Query(None, description="Filter by status"),
    agent_id: str | None = Query(None, description="Filter by agent"),
    limit: int = Query(100, ge=1, le=500),
) -> CommitmentListResponse:
    """List all commitments for the current user."""
    status_filter = CommitmentStatus(status) if status else None
    items = await _store.list_all(
        user_id="default",
        status=status_filter,
        agent_id=agent_id,
        limit=limit,
    )
    return CommitmentListResponse(
        items=[_to_response(i) for i in items],
        total=len(items),
    )


@router.post("/{commitment_id}/dismiss")
async def dismiss_commitment(commitment_id: str) -> dict[str, bool]:
    """Dismiss a commitment (won't be shown again)."""
    now_ms = int(time.time() * 1000)
    count = await _store.mark_status(
        [commitment_id], CommitmentStatus.DISMISSED, now_ms
    )
    if count == 0:
        raise HTTPException(
            status_code=404, detail="Commitment not found or already resolved"
        )
    return {"success": True}


@router.post("/{commitment_id}/snooze")
async def snooze_commitment(commitment_id: str, body: SnoozeRequest) -> dict[str, bool]:
    """Snooze a commitment until a specified time."""
    now_ms = int(time.time() * 1000)
    if body.until_ms <= now_ms:
        raise HTTPException(status_code=400, detail="Snooze time must be in the future")
    updated = await _store.snooze(commitment_id, body.until_ms, now_ms)
    if not updated:
        raise HTTPException(
            status_code=404, detail="Commitment not found or already resolved"
        )
    return {"success": True}
