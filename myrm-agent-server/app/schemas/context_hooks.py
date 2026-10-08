"""Data transfer objects for Pluggable Context Hook Pipeline & Memory Injection API.

[POS]
Defines Pydantic request/response contracts for lifecycle hook execution,
custom agent private/shared memory weaving, and context transformation telemetry.

[INPUT]
- typing, pydantic

[OUTPUT]
- MemoryFragmentDTO, DualLayerWeaveRequest, DualLayerWeaveResponse
- ContextEnvelopeDTO, InterceptStageRequest, InterceptStageResponse
- FullLifecycleRequest, FullLifecycleResponse, ContextHooksStatsResponse
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryFragmentDTO(BaseModel):
    """Granular memory snippet transfer model."""

    fragment_id: str
    layer: str = Field(description="Layer tier: private_agent or shared_global")
    content: str = Field(min_length=1, description="Memory text snippet")
    weight: float = Field(default=1.0, ge=0.1, le=5.0, description="Priority weight")
    tags: list[str] = Field(default_factory=list, description="Descriptive metadata tags")
    agent_id: str | None = Field(default=None, description="Owner agent ID if private")


class DualLayerWeaveRequest(BaseModel):
    """Payload to weave custom agent private and shared memories."""

    agent_id: str = Field(min_length=1, description="Target agent persona ID")
    private_fragments: list[MemoryFragmentDTO] = Field(default_factory=list, description="Private memories")
    shared_fragments: list[MemoryFragmentDTO] = Field(default_factory=list, description="Shared global memories")
    max_token_budget: int = Field(default=1500, ge=100, le=32000, description="Max token budget cap")


class DualLayerWeaveResponse(BaseModel):
    """Result of dual-layer memory weaving."""

    woven_block: str
    private_count: int
    shared_count: int
    estimated_tokens: int


class ContextEnvelopeDTO(BaseModel):
    """Current context state envelope."""

    session_id: str
    agent_id: str
    system_prompt: str
    injected_memories: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    is_blocked: bool = False
    block_reason: str | None = None


class InterceptStageRequest(BaseModel):
    """Payload to execute hooks at a specific stage."""

    stage: str = Field(description="Stage: before_agent_start, context_transform, after_tool_call, before_llm_request")
    envelope: ContextEnvelopeDTO


class HookExecutionReportDTO(BaseModel):
    """Telemetry report for a single hook invocation."""

    hook_id: str
    stage: str
    priority: int
    execution_time_ms: float
    was_modified: bool
    is_blocked: bool


class InterceptStageResponse(BaseModel):
    """Response of a stage interception execution."""

    envelope: ContextEnvelopeDTO
    reports: list[HookExecutionReportDTO]


class FullLifecycleRequest(BaseModel):
    """Payload to run the entire context hook pipeline lifecycle."""

    envelope: ContextEnvelopeDTO
    memory_payload: DualLayerWeaveRequest | None = None


class FullLifecycleResponse(BaseModel):
    """Response of the full lifecycle context hook pipeline execution."""

    envelope: ContextEnvelopeDTO
    stage_reports: dict[str, list[HookExecutionReportDTO]]


class RegisteredHookSummaryDTO(BaseModel):
    """Summary of a registered hook interceptor."""

    hook_id: str
    stage: str
    priority: int
    description: str


class ContextHooksStatsResponse(BaseModel):
    """Statistical metrics for registered lifecycle hooks."""

    total_hooks: int
    before_agent_start: int
    context_transform: int
    after_tool_call: int
    before_llm_request: int
