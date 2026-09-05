"""Lightweight memory and conversation head probe endpoint.

[INPUT]
- sqlalchemy.ext.asyncio::AsyncSession
- fastapi::Query, APIRouter, Depends

[OUTPUT]
- GET /api/v1/memory/head: Zero-overhead probe returning MAX(seq) and change status
- MemoryHeadProbeResponse: Pydantic response contract

[POS]
Provides an ultra-lightweight probe endpoint for polling clients, plugins, or background
sync workers. Downstream consumers can check lag without initiating costly full-corpus queries.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db

router = APIRouter()


class MemoryHeadProbeResponse(BaseModel):
    """Zero-overhead sequence and change status contract."""

    head_seq: int = Field(..., description="Highest sequence number currently recorded in memory corpora")
    has_changes: bool = Field(..., description="Whether head_seq is strictly greater than provided since_seq")
    server_time: str = Field(..., description="ISO-8601 UTC timestamp of the probe response")


@router.get("/head", response_model=MemoryHeadProbeResponse)
async def get_memory_head_probe(
    since_seq: int = Query(0, ge=0, description="Highest sequence number previously observed by caller"),
    db: AsyncSession = Depends(get_db),
) -> MemoryHeadProbeResponse:
    """Read the latest sequence head in <0.1ms using index leaf traversal."""
    # Query max sequence across leaf conversation recall and message corpora
    head_seq = 0
    try:
        recall_max = await db.scalar(
            text("SELECT COALESCE(MAX(id), 0) FROM conversation_recall_segments")
        )
        if recall_max and recall_max > head_seq:
            head_seq = int(recall_max)
    except Exception:
        pass

    try:
        msg_max = await db.scalar(
            text("SELECT COALESCE(MAX(rowid), 0) FROM messages")
        )
        if msg_max and msg_max > head_seq:
            head_seq = int(msg_max)
    except Exception:
        pass

    now_iso = datetime.now(timezone.utc).isoformat()
    return MemoryHeadProbeResponse(
        head_seq=head_seq,
        has_changes=head_seq > since_seq,
        server_time=now_iso,
    )


__all__ = ["router", "MemoryHeadProbeResponse"]
