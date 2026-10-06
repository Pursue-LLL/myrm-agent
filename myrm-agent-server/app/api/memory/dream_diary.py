"""Dream Diary and Surgical Memory Unlearning API endpoints.

[INPUT]
- app.services.memory.dreaming::get_dream_diary_service (POS: 梦境日记业务服务获取)
- myrm_agent_harness.toolkits.memory::DreamDiaryStatus (POS: 梦境日记状态枚举)
- myrm_agent_harness.toolkits.memory::DreamSessionFragment (POS: 会话碎片数据契约)

[OUTPUT]
- router: 梦境日记时间线查询、手动触发、点赞废弃反馈 REST 路由
- unlearn_router: 外科手术式会话记忆遗忘 REST 路由

[POS]
记忆认知中心 HTTP 接入层。暴露人类可读的梦境日记时间线、审核反馈与保留原始聊天历史的会话派生记忆拔除接口。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from myrm_agent_harness.toolkits.memory import (
    DreamDiaryStatus,
    DreamSessionFragment,
)
from pydantic import BaseModel, Field

from app.services.memory.dreaming import get_dream_diary_service

router = APIRouter(prefix="/dream-diary", tags=["memory-dream-diary"])
unlearn_router = APIRouter(prefix="/sessions", tags=["memory-surgical-unlearn"])


class FeedbackRequest(BaseModel):
    """User review feedback payload for a dream diary entry."""

    action: Literal["accept", "reject"] = Field(
        ..., description="Review action: accept or reject"
    )
    reason: str | None = Field(
        default=None, description="Optional rejection reason or feedback notes"
    )


class FragmentPayload(BaseModel):
    """Payload representing a single chat session fragment for dreaming."""

    session_id: str
    memories: list[dict[str, object]] = Field(default_factory=list)
    topic_keywords: list[str] = Field(default_factory=list)
    chat_turn_count: int = 0


class DreamRunRequest(BaseModel):
    """Request payload to manually trigger a grounded dreaming cycle."""

    fragments: list[FragmentPayload] = Field(default_factory=list)


class SurgicalUnlearnRequest(BaseModel):
    """Request payload for surgical session unlearning."""

    memory_items: list[dict[str, object]] = Field(
        default_factory=list,
        description="Memory items to match against target session ID",
    )
    chat_turn_count: int = Field(
        default=0,
        description="Recorded raw chat turn count to preserve",
    )


@router.get("", summary="Get dream diary entries")
async def get_dream_diary(
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filter by entry status: pending, accepted, rejected",
    ),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    """Retrieve list of evolved cognitive insights from idle dreaming cycles."""
    service = get_dream_diary_service()
    status_enum: DreamDiaryStatus | None = None
    if status_filter:
        norm = status_filter.strip().lower()
        if norm in DreamDiaryStatus._value2member_map_:
            status_enum = DreamDiaryStatus(norm)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter '{status_filter}'",
            )

    entries = service.get_entries(status=status_enum, limit=limit)
    return {
        "status": "success",
        "count": len(entries),
        "entries": [e.to_dict() for e in entries],
    }


@router.get("/{entry_id}", summary="Get single dream diary entry")
async def get_dream_diary_entry(entry_id: str) -> dict[str, object]:
    """Retrieve a specific dream diary entry by identifier."""
    service = get_dream_diary_service()
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dream diary entry '{entry_id}' not found",
        )
    return {"status": "success", "entry": entry.to_dict()}


@router.post("/run", summary="Trigger grounded dreaming cycle")
async def run_grounded_dreaming(payload: DreamRunRequest) -> dict[str, object]:
    """Process candidate session fragments into consolidated dream diary entries."""
    service = get_dream_diary_service()
    fragments = [
        DreamSessionFragment(
            session_id=f.session_id,
            memories=f.memories,
            topic_keywords=f.topic_keywords,
            chat_turn_count=f.chat_turn_count,
        )
        for f in payload.fragments
    ]
    new_entries = service.record_dream_cycle(fragments)
    return {
        "status": "success",
        "generated_count": len(new_entries),
        "entries": [e.to_dict() for e in new_entries],
    }


@router.post("/{entry_id}/feedback", summary="Submit feedback on dream entry")
async def submit_entry_feedback(
    entry_id: str, payload: FeedbackRequest
) -> dict[str, object]:
    """Submit approval (accept) or rejection on a specific dream diary entry."""
    service = get_dream_diary_service()
    updated = service.submit_feedback(
        entry_id=entry_id, action=payload.action, reason=payload.reason
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dream diary entry '{entry_id}' not found",
        )
    return {"status": "success", "entry": updated.to_dict()}


@unlearn_router.post("/{session_id}/unlearn", summary="Surgically unlearn session memories")
async def surgical_unlearn_session(
    session_id: str, payload: SurgicalUnlearnRequest
) -> dict[str, object]:
    """Surgically purge long-term memories derived from session_id while keeping chat logs."""
    service = get_dream_diary_service()
    report = await service.unlearn_session(
        session_id=session_id,
        memory_items=payload.memory_items,
        chat_turn_count=payload.chat_turn_count,
    )
    return {
        "status": "success",
        "report": report.to_dict(),
    }
