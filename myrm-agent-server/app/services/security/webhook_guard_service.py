"""Service for Untrusted Webhook Prompt Injection Defense and Toolset Demotion.

[INPUT]
- FilterToolsetRequest, EvaluateExecutionRequest, card_id

[OUTPUT]
- FilterToolsetResponse, EvaluateExecutionResponse, AdminApprovalCardDto

[POS]
- Server security service. Wraps harness webhook_guard subsystem for REST API endpoints.
"""

from __future__ import annotations

import threading

from myrm_agent_harness.core.security.webhook_guard import (
    AdminApprovalCard,
    ApprovalCardStatus,
    DemotedToolAccessDeniedError,
    OriginTaint,
    WebhookToolsetDemoter,
)

from app.schemas.webhook_guard import (
    AdminApprovalCardDto,
    EvaluateExecutionRequest,
    EvaluateExecutionResponse,
    FilterToolsetRequest,
    FilterToolsetResponse,
    OriginTaintDto,
)


class WebhookGuardService:
    """Singleton service managing webhook taint evaluation, tool masking, and admin approval cards."""

    def __init__(self) -> None:
        self._demoter = WebhookToolsetDemoter()

    @staticmethod
    def _convert_taint(taint_dto: OriginTaintDto | None) -> OriginTaint | None:
        """Convert DTO to domain OriginTaint model."""
        if not taint_dto:
            return None
        return OriginTaint(
            is_untrusted_external_content=taint_dto.is_untrusted_external_content,
            origin_source=taint_dto.origin_source,
            sender_identity=taint_dto.sender_identity,
            received_at=taint_dto.received_at,
        )

    @staticmethod
    def _convert_card_to_dto(card: AdminApprovalCard) -> AdminApprovalCardDto:
        """Convert domain AdminApprovalCard model to DTO."""
        return AdminApprovalCardDto(
            card_id=card.card_id,
            task_id=card.task_id,
            origin_source=card.origin_source,
            requested_tool=card.requested_tool,
            tool_arguments=card.tool_arguments,
            risk_reason=card.risk_reason,
            status=card.status.value,
            created_at=card.created_at,
            expires_at=card.expires_at,
        )

    def filter_toolset(self, request: FilterToolsetRequest) -> FilterToolsetResponse:
        """Filter candidate tools down to safe subset if origin is tainted."""
        domain_taint = self._convert_taint(request.taint)
        allowed = self._demoter.filter_available_tools(request.all_tools, domain_taint)
        demoted = [t for t in request.all_tools if t not in allowed]
        is_tainted = domain_taint.is_untrusted_external_content if domain_taint else False

        return FilterToolsetResponse(
            allowed_tools=allowed,
            demoted_tools=demoted,
            is_tainted=is_tainted,
        )

    def evaluate_execution(self, request: EvaluateExecutionRequest) -> EvaluateExecutionResponse:
        """Verify whether tool execution is permitted or escalate to admin approval card."""
        domain_taint = self._convert_taint(request.taint)
        try:
            allowed, card = self._demoter.evaluate_execution(
                task_id=request.task_id,
                tool_name=request.tool_name,
                tool_args=request.tool_arguments,
                taint=domain_taint,
            )
            card_dto = self._convert_card_to_dto(card) if card else None
            return EvaluateExecutionResponse(
                allowed=allowed,
                requires_approval=False,
                card=card_dto,
                message="Tool execution permitted",
            )
        except DemotedToolAccessDeniedError as exc:
            card_obj = self._demoter.get_card(exc.card_id) if exc.card_id else None
            card_dto = self._convert_card_to_dto(card_obj) if card_obj else None
            return EvaluateExecutionResponse(
                allowed=False,
                requires_approval=True,
                card=card_dto,
                message=str(exc),
            )

    def approve_card(self, card_id: str) -> AdminApprovalCardDto:
        """Approve an active escalation card."""
        card = self._demoter.approve_card(card_id)
        return self._convert_card_to_dto(card)

    def reject_card(self, card_id: str) -> AdminApprovalCardDto:
        """Reject and cancel an active escalation card."""
        card = self._demoter.reject_card(card_id)
        return self._convert_card_to_dto(card)

    def get_card(self, card_id: str) -> AdminApprovalCardDto | None:
        """Retrieve an approval card by ID."""
        card = self._demoter.get_card(card_id)
        if not card:
            return None
        return self._convert_card_to_dto(card)

    def list_cards(self, status: str | None = None) -> list[AdminApprovalCardDto]:
        """List all approval cards optionally filtered by status."""
        filter_status = ApprovalCardStatus(status) if status else None
        cards = self._demoter.list_cards(filter_status)
        return [self._convert_card_to_dto(c) for c in cards]


_service_lock = threading.Lock()
_global_webhook_guard_service: WebhookGuardService | None = None


def get_webhook_guard_service() -> WebhookGuardService:
    """Retrieve or initialize the global WebhookGuardService singleton."""
    global _global_webhook_guard_service
    if _global_webhook_guard_service is None:
        with _service_lock:
            if _global_webhook_guard_service is None:
                _global_webhook_guard_service = WebhookGuardService()
    return _global_webhook_guard_service
