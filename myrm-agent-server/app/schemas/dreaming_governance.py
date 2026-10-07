"""Pydantic schemas for Grounded Dreaming Governance and Provenance Auditing.

[POS]
做梦日记治理与溯源 DTO 契约层。定义溯源锚点响应、锁定防遗忘、
一键撤回彻底抹除、人工事实纠偏与闲时调度触发等强类型请求/响应模型。

[INPUT]
- entry_id: 梦境日记条目标识
- action: 审核治理动作
- amended_statement: 人工修正后事实陈述

[OUTPUT]
- ProvenanceAnchorDTO: 消息级双向溯源锚点 DTO
- EntryLockRequest: 日记条目锁定请求
- EntryAmendRequest: 人工纠偏请求
- SchedulerTriggerRequest: 闲时/REM 做梦触发请求
- GovernanceEntryResponse: 包含完整溯源与治理状态的日记响应模型
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProvenanceAnchorDTO(BaseModel):
    """Data transfer object representing an immutable message-level provenance anchor."""

    session_id: str = Field(..., description="Unique chat session ID where evidence originated")
    message_id: str = Field(..., description="Specific message ID within the session")
    speaker: str = Field(default="user", description="Speaker role: user or assistant")
    timestamp: datetime = Field(..., description="UTC timestamp of the source message")
    verbatim_quote: str = Field(..., description="Raw verbatim quotation supporting the insight")
    char_span: tuple[int, int] = Field(default=(0, 0), description="Character slice span in message")
    project_id: str | None = Field(default=None, description="Optional scoped project ID")
    is_personal_profile: bool = Field(default=False, description="Whether insight is global profile")
    hash_digest: str = Field(default="", description="SHA256 integrity hash digest")


class EntryLockRequest(BaseModel):
    """Payload to permanently lock a dream diary insight from forgetting or automatic eviction."""

    reason: str | None = Field(default=None, description="Optional justification for locking entry")


class EntryAmendRequest(BaseModel):
    """Payload for human-in-the-loop manual statement amendment and correction."""

    amended_statement: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Corrected or refined cognitive insight statement",
    )
    amendment_notes: str | None = Field(
        default=None,
        description="Optional reviewer notes detailing why statement was corrected",
    )


class SchedulerTriggerRequest(BaseModel):
    """Payload to trigger idle consolidation or historical REM backfill dreaming."""

    reason: Literal["idle_timeout", "nightly_window", "rem_backfill", "manual"] = Field(
        default="manual",
        description="Reason triggering dreaming cycle",
    )
    target_project_id: str | None = Field(
        default=None,
        description="Optional project scope constraint to isolate facts",
    )
    rem_lookback_days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Lookback window in days for REM historical backfill",
    )


class GovernanceEntryResponse(BaseModel):
    """Full detail of a dream diary entry including governance flags and provenance."""

    entry_id: str = Field(..., description="Unique dream diary entry identifier")
    cognitive_statement: str = Field(..., description="Distilled cognitive insight statement")
    source_session_ids: list[str] = Field(default_factory=list, description="Associated source sessions")
    evidence_snippets: list[str] = Field(default_factory=list, description="Textual evidence quotes")
    confidence_delta: float = Field(..., description="Confidence reinforcement score")
    status: str = Field(..., description="Current status: pending, accepted, rejected, locked, revoked")
    rejection_reason: str | None = Field(default=None, description="Rejection reason if rejected")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    provenance_anchors: list[ProvenanceAnchorDTO] = Field(
        default_factory=list,
        description="Immutable message-level provenance citation anchors",
    )
    project_id: str | None = Field(default=None, description="Project scope constraint")
    is_locked: bool = Field(default=False, description="Whether entry is permanently locked")
    amended_statement: str | None = Field(default=None, description="Human amended statement if any")
