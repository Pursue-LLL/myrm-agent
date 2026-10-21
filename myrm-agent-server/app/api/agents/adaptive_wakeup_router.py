"""FastAPI router for Adaptive Wakeup Driver and bounded wake management (Item 29).

[INPUT]
- app.schemas.adaptive_wakeup::{WakeupBudgetStatusResponse, TriggerAdaptiveWakeupRequest, AdaptiveRoutingResponse, InjectedEventItem, InjectedEventsResponse, HostActivityStateEnum, WakeupChannelEnum, WakeupSourceTypeEnum}
- app.services.agent.adaptive_wakeup::(AdaptiveWakeupService, get_adaptive_wakeup_service)
- myrm_agent_harness.agent.coordination.adaptive_wakeup::{WakeupEvent, WakeupSourceType}

[OUTPUT]
- router mounted on /agents/adaptive-wakeup

[POS]
- HTTP endpoints for supervising session wake budgets, host activity states, and injected settlements.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path, Query
from myrm_agent_harness.agent.coordination.adaptive_wakeup import (
    WakeupEvent,
    WakeupSourceType,
)

from app.schemas.adaptive_wakeup import (
    AdaptiveRoutingResponse,
    HostActivityStateEnum,
    InjectedEventItem,
    InjectedEventsResponse,
    TriggerAdaptiveWakeupRequest,
    WakeupBudgetStatusResponse,
    WakeupChannelEnum,
    WakeupSourceTypeEnum,
)
from app.services.agent.adaptive_wakeup import (
    AdaptiveWakeupService,
    get_adaptive_wakeup_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/adaptive-wakeup", tags=["adaptive-wakeup"])


@router.get("/sessions/{session_id}/budget", response_model=WakeupBudgetStatusResponse)
async def get_session_budget(
    session_id: str = Path(..., description="Unique chat session identifier"),
    service: AdaptiveWakeupService = Depends(get_adaptive_wakeup_service),
) -> WakeupBudgetStatusResponse:
    """Retrieve the current consecutive wake budget and host execution state."""
    budget_state = service.get_budget_state(session_id)
    host_activity = service.get_host_activity(session_id)

    return WakeupBudgetStatusResponse(
        session_id=session_id,
        consecutive_wakes=budget_state.consecutive_wakes,
        max_consecutive_wakes=budget_state.max_consecutive_wakes,
        budget_remaining=budget_state.budget_remaining,
        is_exhausted=budget_state.is_exhausted,
        is_user_stopped=budget_state.is_user_stopped,
        host_activity=HostActivityStateEnum(host_activity.value),
        last_wake_time=budget_state.last_wake_time,
        last_human_reset_time=budget_state.last_human_reset_time,
    )


@router.post("/sessions/{session_id}/human-turn", response_model=WakeupBudgetStatusResponse)
async def record_human_turn(
    session_id: str = Path(..., description="Unique chat session identifier"),
    service: AdaptiveWakeupService = Depends(get_adaptive_wakeup_service),
) -> WakeupBudgetStatusResponse:
    """Notify the router of a human interaction turn, resetting the autonomous wake budget."""
    service.record_human_turn(session_id)
    return await get_session_budget(session_id, service=service)


@router.post("/sessions/{session_id}/stop", response_model=WakeupBudgetStatusResponse)
async def record_user_stop(
    session_id: str = Path(..., description="Unique chat session identifier"),
    service: AdaptiveWakeupService = Depends(get_adaptive_wakeup_service),
) -> WakeupBudgetStatusResponse:
    """Flag the session as stopped by human user, suppressing subsequent background wakes."""
    service.record_user_stop(session_id)
    return await get_session_budget(session_id, service=service)


@router.post("/sessions/{session_id}/settlements", response_model=AdaptiveRoutingResponse)
async def route_settlement(
    payload: TriggerAdaptiveWakeupRequest,
    session_id: str = Path(..., description="Unique chat session identifier"),
    service: AdaptiveWakeupService = Depends(get_adaptive_wakeup_service),
) -> AdaptiveRoutingResponse:
    """Process an asynchronous settlement event and return the routing decision."""
    source_type_map = {
        WakeupSourceTypeEnum.SUBAGENT: WakeupSourceType.SUBAGENT,
        WakeupSourceTypeEnum.BACKGROUND_JOB: WakeupSourceType.BACKGROUND_JOB,
    }

    event = WakeupEvent(
        source_type=source_type_map[payload.source_type],
        source_id=payload.source_id,
        session_id=session_id,
        success=payload.success,
        summary=payload.summary,
        exit_code=payload.exit_code,
        duration_seconds=payload.duration_seconds,
        error=payload.error,
        details=payload.details,
    )

    decision = await service.handle_settlement(event)

    channel_map = {
        "inject": WakeupChannelEnum.INJECT,
        "followup": WakeupChannelEnum.FOLLOWUP,
        "suppress": WakeupChannelEnum.SUPPRESS,
        "degrade": WakeupChannelEnum.DEGRADE,
    }

    return AdaptiveRoutingResponse(
        channel=channel_map[decision.channel.value],
        reason=decision.reason,
        session_id=decision.session_id,
        source_id=decision.source_id,
        consecutive_wakes=decision.consecutive_wakes,
        budget_remaining=decision.budget_remaining,
    )


@router.get("/sessions/{session_id}/injected", response_model=InjectedEventsResponse)
async def list_injected_events(
    session_id: str = Path(..., description="Unique chat session identifier"),
    drain: bool = Query(False, description="Whether to atomically clear queued events"),
    service: AdaptiveWakeupService = Depends(get_adaptive_wakeup_service),
) -> InjectedEventsResponse:
    """Inspect or drain in-flight injected settlement events for a session."""
    if drain:
        events = service.drain_injected_events(session_id)
    else:
        events = service.router.peek_injected_events(session_id)

    items: list[InjectedEventItem] = []
    for ev in events:
        items.append(
            InjectedEventItem(
                source_type=WakeupSourceTypeEnum(ev.source_type.value),
                source_id=ev.source_id,
                session_id=ev.session_id,
                success=ev.success,
                summary=ev.summary,
                exit_code=ev.exit_code,
                duration_seconds=ev.duration_seconds,
                error=ev.error,
                created_at=ev.created_at,
            )
        )

    return InjectedEventsResponse(
        session_id=session_id,
        events=items,
        count=len(items),
    )
