"""Pydantic schemas and DTOs for Listen-Translate-Remember-Act (LTRA) cognitive pipeline.

[POS]
随身感知“听—译—记—办”认知流转 API 数据传输对象层。定义转写摄入请求、
事实四元组响应、自然语言追问响应与一键沙箱任务派发数据契约。

[INPUT]
- 转录分段、说话人别名字典、自然语言追问词、沙箱任务派发参数

[OUTPUT]
- IngestAudioTranscriptRequest, FactDistillResponse, FollowupQueryRequest,
  FollowupQueryResponse, TaskDispatchPlanRequest, DispatchedTaskResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SegmentInputDTO(BaseModel):
    """Single diarized speech segment with millisecond timestamps."""

    model_config = ConfigDict(extra="forbid")

    speaker_id: str = Field(..., description="Raw speaker identifier from diarization engine")
    text: str = Field(..., min_length=1, description="Transcribed utterance text")
    start_ms: int = Field(..., ge=0, description="Start offset in milliseconds")
    end_ms: int = Field(..., ge=0, description="End offset in milliseconds")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Transcription confidence score")


class IngestAudioTranscriptRequest(BaseModel):
    """Payload to ingest diarized transcript and trigger fact distillation."""

    model_config = ConfigDict(extra="forbid")

    segments: list[SegmentInputDTO] = Field(..., min_length=1, description="List of diarized turns")
    audio_id: str = Field(default="voice_session_rec", description="Unique identifier of raw audio recording")
    speaker_aliases: dict[str, str] = Field(default_factory=dict, description="Pre-mapped speaker business names")
    project_id: str | None = Field(default=None, description="Optional scoped project identifier")
    target_agent_id: str | None = Field(default=None, description="Optional target agent identifier")


class AudioTimestampAnchorDTO(BaseModel):
    """Immutable audio slice provenance anchor."""

    model_config = ConfigDict(from_attributes=True)

    audio_id: str
    start_ms: int
    end_ms: int
    verbatim_quote: str
    sha256_digest: str


class CognitiveFactDTO(BaseModel):
    """High-purity distilled cognitive fact quadruple."""

    model_config = ConfigDict(from_attributes=True)

    fact_id: str
    subject: str
    demand: str
    commitment: str
    pending_issue: str
    anchors: list[AudioTimestampAnchorDTO] = Field(default_factory=list)
    project_id: str | None = None
    target_agent_id: str | None = None
    is_confidential: bool = False
    created_at_iso: str


class FactDistillResponse(BaseModel):
    """Response returned upon transcript ingestion and fact distillation."""

    model_config = ConfigDict(extra="forbid")

    status: str = "success"
    audio_id: str
    processed_segments_count: int
    distilled_facts_count: int
    facts: list[CognitiveFactDTO]


class FollowupQueryRequest(BaseModel):
    """Natural language query to recall and cite past conversation facts."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="User question (e.g., 上周张总提了什么需求)")
    project_id: str | None = Field(default=None, description="Filter facts by project")
    target_agent_id: str | None = Field(default=None, description="Filter facts by agent")


class FollowupQueryResponse(BaseModel):
    """Response containing matched facts, citations, and audio slice playback references."""

    model_config = ConfigDict(extra="forbid")

    status: str = "success"
    query: str
    matched_facts_count: int
    facts: list[CognitiveFactDTO]
    suggested_task_draft: dict[str, str] | None = None


class TaskDispatchPlanRequest(BaseModel):
    """Request to generate actionable sandbox task and dispatch to agent execution."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(..., description="Target fact id to act upon")
    target_agent_role: str = Field(default="方案架构专家", description="Target digital agent role")
    custom_instructions: str | None = Field(default=None, description="Additional user instructions")


class DispatchedTaskResponse(BaseModel):
    """Confirmation receipt of dispatched sandbox task."""

    model_config = ConfigDict(extra="forbid")

    status: str = "dispatched"
    task_id: str
    source_fact_id: str
    title: str
    target_agent_role: str
    sandbox_deliverable_path: str
    action_plan_steps: list[str]
    idempotency_token: str
    created_at_iso: str
