"""Pydantic schemas for Dream Cognitive Consolidation and Growth Diary API endpoints.

[POS]
后台梦境认知重组与智能体成长日记 DTO 契约。
提供全链路严格强类型的请求体、响应体与具身演进日记数据传输契约。

[INPUT]
- 前端与运行时触发的梦境重组请求
- 空间治理关联的 Memory Cube 筛选参数

[OUTPUT]
- CognitiveConsolidationRequestDTO: 触发梦境认知重组的请求体
- GrowthDiaryEntryDTO: 人类可读白盒具身成长日记条目 DTO
- CognitiveConsolidationReportDTO: 认知重组端到端执行报告 DTO
- DreamCognitiveOverviewDTO: 认知重组概览统计 DTO
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DreamMotiveTypeEnum(StrEnum):
    """Taxonomy of triggers driving cognitive dream consolidation."""

    NEWNESS = "newness"
    FREQUENCY = "frequency"
    CONFLICT = "conflict"
    FEEDBACK = "feedback"
    FRAGMENTATION = "fragmentation"


class DreamTargetMemoryTypeEnum(StrEnum):
    """Target memory store classification for cognitive mutations."""

    PROFILE = "profile"
    SKILL = "skill"
    RULE = "rule"
    INSIGHT = "insight"
    ARCHIVE = "archive"


class DreamCognitiveActionTypeEnum(StrEnum):
    """Mutation intent emitted by cognitive dream reflection."""

    CREATE = "create"
    UPDATE = "update"
    MERGE = "merge"
    ARCHIVE = "archive"


class EvidenceAnchorDTO(BaseModel):
    """Verbatim quote evidence anchor."""

    model_config = ConfigDict(frozen=True)

    message_id: str = Field(..., description="Message identifier")
    speaker: str = Field(default="user", description="Speaker name")
    verbatim_quote: str = Field(..., description="Verbatim cited quote")


class MemoryFactPayloadDTO(BaseModel):
    """Single conversational memory fact with optional evidence."""

    model_config = ConfigDict(frozen=True)

    fact_id: str | None = Field(default=None, description="Optional fact ID")
    content: str = Field(..., description="Fact content")
    evidence: list[EvidenceAnchorDTO] = Field(default_factory=list, description="Evidence citations")


class SessionFragmentPayloadDTO(BaseModel):
    """Chat session fragment input for dream consolidation."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., description="Origin session identifier")
    project_id: str | None = Field(default=None, description="Target project isolation scope")
    chat_turn_count: int = Field(default=1, ge=1, description="Chat turn count")
    memories: list[MemoryFactPayloadDTO] = Field(default_factory=list, description="Extracted memory facts")


class CognitiveConsolidationRequestDTO(BaseModel):
    """Request payload to trigger background cognitive consolidation."""

    model_config = ConfigDict(frozen=True)

    fragments: list[SessionFragmentPayloadDTO] = Field(..., description="Session fragments to consolidate")
    cube_id: str | None = Field(default=None, description="Associated Memory Cube scope")
    target_project_id: str | None = Field(default=None, description="Project scope isolation constraint")


class HypotheticalDeductionDTO(BaseModel):
    """Hypothetical deduction validating cognitive future utility."""

    model_config = ConfigDict(frozen=True)

    hypothetical_query: str = Field(..., description="Target query that benefits from insight")
    improved_response_reasoning: str = Field(..., description="Reasoning gain and decision improvement")
    confidence_gain: float = Field(default=0.25, description="Confidence improvement delta")


class DreamCognitiveActionDTO(BaseModel):
    """Actionable memory mutation emitted by cognitive dreaming."""

    model_config = ConfigDict(frozen=True)

    action_id: str = Field(..., description="Unique action ID")
    action_type: DreamCognitiveActionTypeEnum = Field(..., description="Mutation type")
    target_type: DreamTargetMemoryTypeEnum = Field(..., description="Target memory type")
    target_id: str | None = Field(default=None, description="Target memory identifier")
    source_fact_ids: list[str] = Field(default_factory=list, description="Source fact IDs")
    payload_statement: str = Field(..., description="Synthesized cognitive statement")
    deduction: HypotheticalDeductionDTO = Field(..., description="Deductive justification")
    confidence: float = Field(..., description="Consolidated confidence score")
    cube_id: str | None = Field(default=None, description="Target Memory Cube ID")


class GrowthDiaryEntryDTO(BaseModel):
    """Human-readable embodiment journal entry of AI mind evolution."""

    model_config = ConfigDict(frozen=True)

    diary_id: str = Field(..., description="Unique diary identifier")
    title: str = Field(..., description="Embodied evolution title")
    summary: str = Field(..., description="Core insight summary")
    reflective_narrative: str = Field(..., description="Embodied self-reflection prose")
    motive_type: DreamMotiveTypeEnum = Field(..., description="Underlying trigger motive")
    themes: list[str] = Field(default_factory=list, description="Mind evolution topic tags")
    cube_id: str | None = Field(default=None, description="Associated Memory Cube")
    generated_actions: list[DreamCognitiveActionDTO] = Field(default_factory=list, description="Emitted actions")
    created_at: datetime = Field(..., description="Generation timestamp")


class CognitiveConsolidationReportDTO(BaseModel):
    """Comprehensive execution report of cognitive consolidation run."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(..., description="Unique run identifier")
    cube_id: str | None = Field(default=None, description="Memory Cube ID")
    timestamp: datetime = Field(..., description="Execution timestamp")
    duration_ms: float = Field(..., description="Execution duration in ms")
    input_fact_count: int = Field(..., description="Input memory fact count")
    clusters_formed: int = Field(..., description="Number of cognitive clusters formed")
    actions_generated: int = Field(..., description="Count of cognitive actions generated")
    diary_entries: list[GrowthDiaryEntryDTO] = Field(default_factory=list, description="Generated diaries")


class DreamCognitiveOverviewDTO(BaseModel):
    """High-level summary of dream cognitive system status."""

    model_config = ConfigDict(frozen=True)

    total_diaries: int = Field(..., description="Total recorded growth diaries")
    total_actions: int = Field(..., description="Total cognitive mutation actions")
    active_cubes: list[str] = Field(default_factory=list, description="List of cubes with diaries")
    latest_run_id: str | None = Field(default=None, description="Latest run ID")
