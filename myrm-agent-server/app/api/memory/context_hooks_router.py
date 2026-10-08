"""REST API router for Pluggable Context Hook Pipeline & Memory Injection.

[POS]
Provides HTTP endpoints for executing lifecycle context hooks, weaving
dual-layer custom agent memories, and auditing egress transformations.

[INPUT]
- fastapi
- app.schemas.context_hooks
- app.services.memory.context_hooks.provider
- myrm_agent_harness.toolkits.memory

[OUTPUT]
- router (FastAPI APIRouter)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from myrm_agent_harness.toolkits.memory import (
    ContextEnvelope,
    ContextHookStage,
    DualLayerMemoryPayload,
    MemoryFragment,
    MemoryLayerKind,
)

from app.schemas.context_hooks import (
    ContextEnvelopeDTO,
    ContextHooksStatsResponse,
    DualLayerWeaveRequest,
    DualLayerWeaveResponse,
    FullLifecycleRequest,
    FullLifecycleResponse,
    HookExecutionReportDTO,
    InterceptStageRequest,
    InterceptStageResponse,
    MemoryFragmentDTO,
    RegisteredHookSummaryDTO,
)
from app.services.memory.context_hooks.provider import (
    get_context_hook_suite,
)

router = APIRouter(prefix="/context-hooks", tags=["Pluggable Context Hooks & Memory Injection"])


def _dto_to_envelope(dto: ContextEnvelopeDTO) -> ContextEnvelope:
    return ContextEnvelope(
        session_id=dto.session_id,
        agent_id=dto.agent_id,
        system_prompt=dto.system_prompt,
        injected_memories=list(dto.injected_memories),
        metadata=dict(dto.metadata),
        is_blocked=dto.is_blocked,
        block_reason=dto.block_reason,
    )


def _envelope_to_dto(env: ContextEnvelope) -> ContextEnvelopeDTO:
    return ContextEnvelopeDTO(
        session_id=env.session_id,
        agent_id=env.agent_id,
        system_prompt=env.system_prompt,
        injected_memories=list(env.injected_memories),
        metadata=dict(env.metadata),
        is_blocked=env.is_blocked,
        block_reason=env.block_reason,
    )


def _dto_to_fragment(dto: MemoryFragmentDTO) -> MemoryFragment:
    try:
        layer_enum = MemoryLayerKind(dto.layer)
    except ValueError:
        layer_enum = MemoryLayerKind.SHARED_GLOBAL
    return MemoryFragment(
        fragment_id=dto.fragment_id,
        layer=layer_enum,
        content=dto.content,
        weight=dto.weight,
        tags=list(dto.tags),
        agent_id=dto.agent_id,
    )


@router.post("/pipeline/intercept", response_model=InterceptStageResponse)
async def intercept_stage(req: InterceptStageRequest) -> InterceptStageResponse:
    """Execute all registered hooks for a specified lifecycle stage."""
    suite = get_context_hook_suite()
    try:
        stage_enum = ContextHookStage(req.stage)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown hook lifecycle stage '{req.stage}'",
        ) from None

    env = _dto_to_envelope(req.envelope)
    reports = suite.execute_stage(stage=stage_enum, envelope=env)

    report_dtos = [
        HookExecutionReportDTO(
            hook_id=r.hook_id,
            stage=r.stage.value,
            priority=r.priority,
            execution_time_ms=r.execution_time_ms,
            was_modified=r.was_modified,
            is_blocked=r.is_blocked,
        )
        for r in reports
    ]

    return InterceptStageResponse(
        envelope=_envelope_to_dto(env),
        reports=report_dtos,
    )


@router.post("/weave-memory", response_model=DualLayerWeaveResponse)
async def weave_memory(req: DualLayerWeaveRequest) -> DualLayerWeaveResponse:
    """Weave custom agent private memories with shared global preferences."""
    suite = get_context_hook_suite()

    privates = [_dto_to_fragment(f) for f in req.private_fragments]
    shared = [_dto_to_fragment(f) for f in req.shared_fragments]

    payload = DualLayerMemoryPayload(
        agent_id=req.agent_id,
        private_fragments=privates,
        shared_fragments=shared,
        max_token_budget=req.max_token_budget,
    )

    outcome = suite.weave_memories(payload)
    return DualLayerWeaveResponse(
        woven_block=outcome.woven_block,
        private_count=outcome.private_count,
        shared_count=outcome.shared_count,
        estimated_tokens=outcome.estimated_tokens,
    )


@router.post("/pipeline/full-lifecycle", response_model=FullLifecycleResponse)
async def full_lifecycle_pipeline(req: FullLifecycleRequest) -> FullLifecycleResponse:
    """Run standard context lifecycle pipeline with dual-layer memory weaving."""
    suite = get_context_hook_suite()
    env = _dto_to_envelope(req.envelope)

    payload: DualLayerMemoryPayload | None = None
    if req.memory_payload is not None:
        privates = [_dto_to_fragment(f) for f in req.memory_payload.private_fragments]
        shared = [_dto_to_fragment(f) for f in req.memory_payload.shared_fragments]
        payload = DualLayerMemoryPayload(
            agent_id=req.memory_payload.agent_id,
            private_fragments=privates,
            shared_fragments=shared,
            max_token_budget=req.memory_payload.max_token_budget,
        )

    lifecycle_reports = suite.execute_full_lifecycle(envelope=env, memory_payload=payload)

    serialized_reports: dict[str, list[HookExecutionReportDTO]] = {}
    for stg_key, reps in lifecycle_reports.items():
        serialized_reports[stg_key] = [
            HookExecutionReportDTO(
                hook_id=r.hook_id,
                stage=r.stage.value,
                priority=r.priority,
                execution_time_ms=r.execution_time_ms,
                was_modified=r.was_modified,
                is_blocked=r.is_blocked,
            )
            for r in reps
        ]

    return FullLifecycleResponse(
        envelope=_envelope_to_dto(env),
        stage_reports=serialized_reports,
    )


@router.get("/stages", response_model=list[RegisteredHookSummaryDTO])
async def list_registered_hooks(
    stage: str | None = Query(default=None, description="Optional stage filter"),
) -> list[RegisteredHookSummaryDTO]:
    """List all registered lifecycle hooks."""
    suite = get_context_hook_suite()
    stage_enum: ContextHookStage | None = None
    if stage:
        try:
            stage_enum = ContextHookStage(stage)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown stage '{stage}'",
            ) from None

    hooks = suite.list_hooks(stage=stage_enum)
    return [
        RegisteredHookSummaryDTO(
            hook_id=h.hook_id,
            stage=h.stage.value,
            priority=h.priority,
            description=h.description,
        )
        for h in hooks
    ]


@router.get("/stats", response_model=ContextHooksStatsResponse)
async def get_stats() -> ContextHooksStatsResponse:
    """Retrieve telemetry metrics for the context hook pipeline."""
    suite = get_context_hook_suite()
    s = suite.get_stats()
    return ContextHooksStatsResponse(
        total_hooks=s["total_hooks"],
        before_agent_start=s["before_agent_start"],
        context_transform=s["context_transform"],
        after_tool_call=s["after_tool_call"],
        before_llm_request=s["before_llm_request"],
    )
