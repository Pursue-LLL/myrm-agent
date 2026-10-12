"""Service layer for HITL Denial Events and Synthetic Tool Result Generation.

[INPUT]
- ProcessDenialsRequest DTO.

[OUTPUT]
- ProcessDenialsResponse DTO.

[POS]
- Server service encapsulating AgentScope-Java #2546 HITL denial handling.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.hitl_denial import (
    DenialResolutionPolicy,
    HitlDenialManager,
    ProcessDenialsResult,
    ToolDenialItem,
)

from app.schemas.hitl_denial import (
    DenialResolutionPolicyDto,
    ProcessDenialsRequest,
    ProcessDenialsResponse,
    SyntheticToolResultBlockDto,
)

logger = logging.getLogger(__name__)


class HitlDenialService:
    """Service providing synthetic tool result emission upon user HITL denials."""

    def __init__(self, manager: HitlDenialManager | None = None) -> None:
        self._manager = manager or HitlDenialManager()

    def process_denials(self, request: ProcessDenialsRequest) -> ProcessDenialsResponse:
        """Process manual tool denials into context-preserving synthetic tool results."""
        domain_items = [
            ToolDenialItem(
                tool_call_id=item.tool_call_id,
                tool_name=item.tool_name,
                reason=item.reason,
                custom_feedback=item.custom_feedback,
            )
            for item in request.denied_items
        ]

        override_policy = (
            DenialResolutionPolicy(request.override_policy.value)
            if request.override_policy
            else None
        )

        res: ProcessDenialsResult = self._manager.process_denials(
            denied_items=domain_items,
            total_tool_calls_in_step=request.total_tool_calls_in_step,
            override_policy=override_policy,
        )

        synthetic_dtos = [
            SyntheticToolResultBlockDto(
                tool_call_id=s.tool_call_id,
                tool_name=s.tool_name,
                output=s.output,
                is_error=s.is_error,
                metadata=s.metadata,
            )
            for s in res.synthetic_results
        ]

        return ProcessDenialsResponse(
            all_tools_denied=res.all_tools_denied,
            total_requested=res.total_requested,
            total_denied=res.total_denied,
            resolution_action=DenialResolutionPolicyDto(res.resolution_action.value),
            synthetic_results=synthetic_dtos,
            stop_requested=res.stop_requested,
        )
