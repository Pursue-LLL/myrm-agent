"""Service layer handling HITL denial event generation and audit orchestration.

[INPUT]
- ProcessHitlDecisionsRequest schema from API router.

[OUTPUT]
- ProcessHitlDecisionsResponse containing converted event DTOs.

[POS]
- Bridge between FastAPI request layer and core Harness HitlDenialEventDispatcher.
"""

from __future__ import annotations

import logging
from typing import Literal

from myrm_agent_harness.core.security.hitl_denial_events import (
    AllToolsDeniedPolicy,
    AllToolsDeniedPolicyEvaluator,
    ConfirmResult,
    HitlDenialEventDispatcher,
    HitlProcessOutcome,
    ToolUseBlock,
)

from app.schemas.hitl_denial_events import (
    AllToolsDeniedEventDto,
    HitlPoliciesConfigResponse,
    ProcessHitlDecisionsRequest,
    ProcessHitlDecisionsResponse,
    ToolResultEventDto,
)

logger = logging.getLogger(__name__)

STRICT_HALT_DEFAULT_TOOLS: list[str] = [
    "bash_exec",
    "shell_exec",
    "rm_destructive",
    "drop_database",
]


class HitlDenialEventsService:
    """Service mediating human-in-the-loop decision processing and event emission."""

    def __init__(
        self,
        dispatcher: HitlDenialEventDispatcher | None = None,
    ) -> None:
        """Initialize service with dispatcher and policies."""
        if dispatcher is not None:
            self._dispatcher = dispatcher
        else:
            evaluator = AllToolsDeniedPolicyEvaluator(
                default_policy=AllToolsDeniedPolicy.HALT,
                strict_halt_tools=STRICT_HALT_DEFAULT_TOOLS,
            )
            self._dispatcher = HitlDenialEventDispatcher(policy_evaluator=evaluator)

    def process_decisions(
        self,
        request: ProcessHitlDecisionsRequest,
    ) -> ProcessHitlDecisionsResponse:
        """Execute decision processing and return structured event responses."""
        logger.info(
            "Processing HITL decisions for session %s, step %s with %d calls",
            request.session_id,
            request.step_id,
            len(request.tool_calls),
        )

        harness_tool_calls = [
            ToolUseBlock(
                id=tc.id,
                name=tc.name,
                arguments=tc.arguments,
            )
            for tc in request.tool_calls
        ]

        harness_decisions = [
            ConfirmResult(
                tool_call_id=d.tool_call_id,
                tool_name=d.tool_name,
                confirmed=d.confirmed,
                reason=d.reason,
            )
            for d in request.decisions
        ]

        explicit_policy: AllToolsDeniedPolicy | None = None
        if request.policy is not None:
            explicit_policy = AllToolsDeniedPolicy(request.policy)

        outcome: HitlProcessOutcome = self._dispatcher.process_decisions(
            session_id=request.session_id,
            step_id=request.step_id,
            tool_calls=harness_tool_calls,
            decisions=harness_decisions,
            explicit_policy=explicit_policy,
        )

        tool_result_dtos: list[ToolResultEventDto] = [
            ToolResultEventDto(
                event_id=ev.event_id,
                tool_call_id=ev.tool_call_id,
                tool_name=ev.tool_name,
                state=self._map_state(ev.state.value),
                output_text=ev.output_text,
                created_at=ev.created_at,
            )
            for ev in outcome.tool_result_events
        ]

        all_denied_dto: AllToolsDeniedEventDto | None = None
        if outcome.all_tools_denied_event is not None:
            all_denied_ev = outcome.all_tools_denied_event
            all_denied_dto = AllToolsDeniedEventDto(
                event_id=all_denied_ev.event_id,
                session_id=all_denied_ev.session_id,
                step_id=all_denied_ev.step_id,
                policy_applied=self._map_policy(
                    all_denied_ev.policy_applied.value
                ),
                should_stop=all_denied_ev.should_stop,
                stop_reason=all_denied_ev.stop_reason,
                denied_tool_count=len(all_denied_ev.denied_tool_calls),
                created_at=all_denied_ev.created_at,
            )

        return ProcessHitlDecisionsResponse(
            session_id=outcome.session_id,
            step_id=outcome.step_id,
            total_calls=outcome.total_calls,
            confirmed_count=outcome.confirmed_count,
            denied_count=outcome.denied_count,
            all_denied=outcome.all_denied,
            tool_result_events=tool_result_dtos,
            all_tools_denied_event=all_denied_dto,
            can_resume=outcome.can_resume,
            terminal_reason=outcome.terminal_reason,
        )

    def get_policies_config(self) -> HitlPoliciesConfigResponse:
        """Retrieve available policy types and configuration."""
        return HitlPoliciesConfigResponse(
            available_policies=[p.value for p in AllToolsDeniedPolicy],
            default_policy=AllToolsDeniedPolicy.HALT.value,
            strict_halt_tools=list(STRICT_HALT_DEFAULT_TOOLS),
        )

    @staticmethod
    def _map_state(state_str: str) -> Literal["ALLOWED", "DENIED", "ERROR"]:
        if state_str == "ALLOWED":
            return "ALLOWED"
        if state_str == "DENIED":
            return "DENIED"
        return "ERROR"

    @staticmethod
    def _map_policy(
        policy_str: str,
    ) -> Literal["HALT", "RESUME_WITH_FEEDBACK"]:
        if policy_str == "RESUME_WITH_FEEDBACK":
            return "RESUME_WITH_FEEDBACK"
        return "HALT"


_service_instance: HitlDenialEventsService | None = None


def get_hitl_denial_events_service() -> HitlDenialEventsService:
    """Dependency injector for HitlDenialEventsService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = HitlDenialEventsService()
    return _service_instance
