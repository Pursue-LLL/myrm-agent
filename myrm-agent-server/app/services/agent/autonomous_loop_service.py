"""[INPUT] StartAutonomousLoopRequest, AdvanceStepRequest, SetModeRequest, CompleteLoopRequest.
[OUTPUT] AutonomousLoopService providing autonomous loop lifecycle management, pacing, and watchdog monitoring.
[POS] Service layer for Goal-Driven Autonomous Orchestration Loop (Item 38).
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.coordination.autonomous_loop import (
    AutonomousLoopConfig,
    AutonomousLoopController,
    AutonomousLoopState,
    AutonomousLoopStep,
    OrchestrationMode,
)

from app.schemas.autonomous_loop import (
    AdvanceStepRequest,
    AutonomousLoopConfigDTO,
    AutonomousLoopStateResponse,
    AutonomousLoopStepDTO,
    CompleteLoopRequest,
    OrchestrationModeEnum,
    SetModeRequest,
    StartAutonomousLoopRequest,
    StepStatusEnum,
)

logger = logging.getLogger(__name__)


def _to_step_dto(step: AutonomousLoopStep) -> AutonomousLoopStepDTO:
    return AutonomousLoopStepDTO(
        step_index=step.step_index,
        action_type=step.action_type,
        description=step.description,
        status=StepStatusEnum(step.status.value),
        timestamp=step.timestamp,
        metadata=dict(step.metadata),
    )


def _to_state_response(state: AutonomousLoopState) -> AutonomousLoopStateResponse:
    return AutonomousLoopStateResponse(
        session_id=state.session_id,
        goal_id=state.goal_id,
        mode=OrchestrationModeEnum(state.mode.value),
        current_step=state.current_step,
        max_steps=state.max_steps,
        is_active=state.is_active,
        history=[_to_step_dto(s) for s in state.history],
        pause_reason=state.pause_reason,
        started_at=state.started_at,
        last_advanced_at=state.last_advanced_at,
    )


def _to_domain_config(dto: AutonomousLoopConfigDTO | None) -> AutonomousLoopConfig:
    if dto is None:
        return AutonomousLoopConfig()
    return AutonomousLoopConfig(
        max_autonomous_steps=dto.max_autonomous_steps,
        pause_on_approval=dto.pause_on_approval,
        pause_on_error=dto.pause_on_error,
        heartbeat_interval_s=dto.heartbeat_interval_s,
    )


class AutonomousLoopService:
    """Session-scoped autonomous loop coordination and pacing governance."""

    def __init__(self, controller: AutonomousLoopController | None = None) -> None:
        self._controller = controller or AutonomousLoopController()

    def start_loop(self, req: StartAutonomousLoopRequest) -> AutonomousLoopStateResponse:
        """Start a new autonomous or supervised orchestration loop."""
        mode = OrchestrationMode(req.mode.value)
        cfg = _to_domain_config(req.config)
        domain_state = self._controller.start_loop(
            session_id=req.session_id,
            goal_id=req.goal_id,
            mode=mode,
            config=cfg,
        )
        return _to_state_response(domain_state)

    def advance_step(self, session_id: str, req: AdvanceStepRequest) -> AutonomousLoopStateResponse:
        """Advance the autonomous orchestration loop by one action step."""
        domain_state = self._controller.advance_step(
            session_id=session_id,
            action_type=req.action_type,
            description=req.description,
            requires_approval=req.requires_approval,
            is_error=req.is_error,
            metadata=req.metadata,
        )
        return _to_state_response(domain_state)

    def set_mode(self, session_id: str, req: SetModeRequest) -> AutonomousLoopStateResponse:
        """Switch orchestration mode between Autonomous, Supervised, and Paused."""
        domain_mode = OrchestrationMode(req.mode.value)
        domain_state = self._controller.set_mode(
            session_id=session_id,
            mode=domain_mode,
            reason=req.reason,
        )
        return _to_state_response(domain_state)

    def complete_loop(self, session_id: str, req: CompleteLoopRequest) -> AutonomousLoopStateResponse:
        """Conclude an autonomous loop successfully."""
        domain_state = self._controller.complete_loop(
            session_id=session_id,
            summary=req.summary,
        )
        return _to_state_response(domain_state)

    def get_state(self, session_id: str) -> AutonomousLoopStateResponse | None:
        """Retrieve current loop state for session, if any."""
        state = self._controller.get_state(session_id)
        if state is None:
            return None
        return _to_state_response(state)

    def list_loops(self) -> list[AutonomousLoopStateResponse]:
        """List all active or registered orchestration loops."""
        states = self._controller.list_active_loops()
        return [_to_state_response(s) for s in states]

    def reset_loop(self, session_id: str) -> bool:
        """Reset and remove loop tracking for session."""
        return self._controller.reset_loop(session_id)


_service_lock = threading.Lock()
_global_service: AutonomousLoopService | None = None


def get_autonomous_loop_service() -> AutonomousLoopService:
    """Retrieve global thread-safe AutonomousLoopService instance."""
    global _global_service
    if _global_service is None:
        with _service_lock:
            if _global_service is None:
                _global_service = AutonomousLoopService()
    return _global_service
