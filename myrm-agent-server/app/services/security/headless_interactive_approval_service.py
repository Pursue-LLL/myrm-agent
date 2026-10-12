"""Service layer for Headless Agent Interactive Approval, Webhook Relay, and Hold-Resume Suite.

[POS] app/services/security/headless_interactive_approval_service.py
[INPUT] app.schemas.headless_interactive_approval, myrm_agent_harness.core.security.headless_interactive_approval
[OUTPUT] HeadlessInteractiveApprovalService, get_headless_approval_service
"""

from __future__ import annotations

import logging
from typing import Final

from myrm_agent_harness.core.security.headless_interactive_approval import (
    ApprovalHoldStatus,
    ApprovalHoldTicket,
    HeadlessHoldStateMachine,
    InteractiveApprovalWebhookRelay,
    RiskActionDescriptor,
    StreamingContinuationConduit,
)

from app.schemas.headless_interactive_approval import (
    CreateHoldTicketRequest,
    FormatStreamHoldNoticeRequest,
    HoldTicketDTO,
    RiskActionDTO,
    StreamHoldChunkDTO,
    SubmitApprovalDecisionRequest,
    SubmitApprovalDecisionResponse,
    WebhookEndpointConfigRequest,
    WebhookRelayPayloadDTO,
)

logger: Final[logging.Logger] = logging.getLogger(__name__)


class HeadlessInteractiveApprovalService:
    """Coordinates hold-state tickets, external notification relays, and stream reasoning injection."""

    def __init__(self, base_approval_url: str = "http://localhost:3000/approve") -> None:
        self._state_machine = HeadlessHoldStateMachine(base_approval_url=base_approval_url)
        self._webhook_relay = InteractiveApprovalWebhookRelay()
        self._conduit = StreamingContinuationConduit()

    def create_hold_ticket(self, request: CreateHoldTicketRequest) -> HoldTicketDTO:
        """Create an ephemeral hold ticket and return its representation with approval shortlink."""
        action_desc = RiskActionDescriptor(
            action_id=request.action.action_id,
            tool_name=request.action.tool_name,
            command_or_target=request.action.command_or_target,
            risk_level=request.action.risk_level,
            justification=request.action.justification,
        )

        ticket = self._state_machine.create_hold_ticket(
            session_id=request.session_id,
            action=action_desc,
            timeout_seconds=request.timeout_seconds,
        )

        logger.info(
            "Created hold ticket tx=%s for tool=%s",
            ticket.tx_id,
            ticket.action.tool_name,
        )
        return self._ticket_to_dto(ticket)

    def get_ticket(self, tx_id: str) -> HoldTicketDTO | None:
        """Query status and details of a hold ticket."""
        ticket = self._state_machine.get_ticket(tx_id)
        if ticket is None:
            return None
        return self._ticket_to_dto(ticket)

    def submit_decision(
        self,
        tx_id: str,
        request: SubmitApprovalDecisionRequest,
    ) -> SubmitApprovalDecisionResponse:
        """Atomically record an operator decision on a hold ticket."""
        decision_enum = ApprovalHoldStatus(request.decision.upper())
        updated_ticket = self._state_machine.submit_decision(
            tx_id=tx_id,
            decision=decision_enum,
            operator=request.operator,
            notes=request.notes,
        )

        is_resumed = updated_ticket.status in (
            ApprovalHoldStatus.APPROVED,
            ApprovalHoldStatus.REJECTED,
        )

        return SubmitApprovalDecisionResponse(
            ticket=self._ticket_to_dto(updated_ticket),
            resumed=is_resumed,
        )

    async def wait_for_ticket_resolution(
        self,
        tx_id: str,
        timeout_seconds: float | None = None,
    ) -> HoldTicketDTO:
        """Asynchronously await ticket decision or timeout."""
        resolved = await self._state_machine.wait_for_decision(
            tx_id=tx_id,
            timeout_seconds=timeout_seconds,
        )
        return self._ticket_to_dto(resolved)

    def register_webhook_endpoint(self, request: WebhookEndpointConfigRequest) -> dict[str, str]:
        """Register an outbound webhook destination URL."""
        self._webhook_relay.register_endpoint(name=request.name, url=request.url)
        return self._webhook_relay.list_endpoints()

    def list_webhook_endpoints(self) -> dict[str, str]:
        """Return all registered webhook endpoints."""
        return self._webhook_relay.list_endpoints()

    def get_relay_payload(
        self,
        tx_id: str,
        custom_metadata: dict[str, str] | None = None,
    ) -> WebhookRelayPayloadDTO | None:
        """Build standardized relay payload for a hold ticket."""
        ticket = self._state_machine.get_ticket(tx_id)
        if ticket is None:
            return None

        payload = self._webhook_relay.build_payload(ticket, custom_metadata=custom_metadata)
        return WebhookRelayPayloadDTO(
            tx_id=payload.tx_id,
            session_id=payload.session_id,
            tool_name=payload.tool_name,
            command_or_target=payload.command_or_target,
            risk_level=payload.risk_level,
            approval_shortlink=payload.approval_shortlink,
            expires_in_seconds=payload.expires_in_seconds,
            custom_metadata=dict(payload.custom_metadata),
        )

    def format_stream_notice(
        self, request: FormatStreamHoldNoticeRequest
    ) -> StreamHoldChunkDTO:
        """Format an in-stream reasoning markdown chunk."""
        ticket = self._state_machine.get_ticket(request.tx_id)
        if ticket is None:
            msg = f"Hold ticket '{request.tx_id}' not found."
            raise KeyError(msg)

        if request.is_resumed:
            chunk = self._conduit.format_resumed_reasoning_block(ticket)
        else:
            chunk = self._conduit.format_hold_reasoning_block(ticket)

        return StreamHoldChunkDTO(
            tx_id=chunk.tx_id,
            inject_markdown=chunk.inject_markdown,
            is_resumed=chunk.is_resumed,
            status=chunk.status.value,
        )

    @staticmethod
    def _ticket_to_dto(ticket: ApprovalHoldTicket) -> HoldTicketDTO:
        """Convert a Harness ApprovalHoldTicket to a typed REST DTO."""
        return HoldTicketDTO(
            tx_id=ticket.tx_id,
            session_id=ticket.session_id,
            action=RiskActionDTO(
                action_id=ticket.action.action_id,
                tool_name=ticket.action.tool_name,
                command_or_target=ticket.action.command_or_target,
                risk_level=ticket.action.risk_level,
                justification=ticket.action.justification,
            ),
            status=ticket.status.value,
            shortlink_url=ticket.shortlink_url,
            created_at=ticket.created_at,
            expires_at=ticket.expires_at,
            operator_decision_notes=ticket.operator_decision_notes,
            decided_by=ticket.decided_by,
            decided_at=ticket.decided_at,
        )


_service_instance: HeadlessInteractiveApprovalService | None = None


def get_headless_approval_service() -> HeadlessInteractiveApprovalService:
    """Return global HeadlessInteractiveApprovalService singleton instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = HeadlessInteractiveApprovalService()
    return _service_instance
