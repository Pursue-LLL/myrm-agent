"""Service layer for Native Credential Approvals and Precise Message Links.

[INPUT]
- CreateCredentialAskRequest, DecideCredentialAskRequest DTOs.

[OUTPUT]
- CredentialAskDto, DecideCredentialAskResponse, PendingAsksResponse DTOs.

[POS]
- Server service layer providing QM #1502 native credential approval and session message linking.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.native_credential_approval import (
    ApprovalAuditRecord,
    ApprovalDecision,
    CredentialAsk,
    NativeCredentialApprovalManager,
)

from app.schemas.native_credential_approval import (
    ApprovalAuditRecordDto,
    CreateCredentialAskRequest,
    CredentialAskDto,
    DecideCredentialAskRequest,
    DecideCredentialAskResponse,
    MessageSequenceRefDto,
    PendingAsksResponse,
    PreciseMessageLinkDto,
)

logger = logging.getLogger(__name__)


def _to_dto_ask(ask: CredentialAsk) -> CredentialAskDto:
    """Convert harness CredentialAsk domain object to API DTO."""
    msg_ref_dto = MessageSequenceRefDto(
        session_id=ask.message_ref.session_id,
        message_id=ask.message_ref.message_id,
        sequence_number=ask.message_ref.sequence_number,
        turn_index=ask.message_ref.turn_index,
    )
    deep_link_dto = PreciseMessageLinkDto(
        path=ask.deep_link.path,
        sequence_number=ask.deep_link.sequence_number,
        message_id=ask.deep_link.message_id,
        deep_link_url=ask.deep_link.deep_link_url,
    )
    return CredentialAskDto(
        ask_id=ask.ask_id,
        credential_id=ask.credential_id,
        service_name=ask.service_name,
        account_label=ask.account_label,
        requester_id=ask.requester_id,
        owner_id=ask.owner_id,
        purpose=ask.purpose,
        message_ref=msg_ref_dto,
        deep_link=deep_link_dto,
        status=ask.status.value,
        decision_mode=ask.decision_mode.value if ask.decision_mode else None,
        decided_by=ask.decided_by,
        decision_note=ask.decision_note,
        created_at_iso=ask.created_at_iso,
        decided_at_iso=ask.decided_at_iso,
    )


def _to_dto_audit(record: ApprovalAuditRecord) -> ApprovalAuditRecordDto:
    """Convert harness ApprovalAuditRecord domain object to API DTO."""
    return ApprovalAuditRecordDto(
        audit_id=record.audit_id,
        ask_id=record.ask_id,
        credential_id=record.credential_id,
        service_name=record.service_name,
        actor_id=record.actor_id,
        decision=record.decision.value,
        target_session_id=record.target_session_id,
        sequence_number=record.sequence_number,
        timestamp_iso=record.timestamp_iso,
        note=record.note,
    )


class NativeCredentialApprovalService:
    """Service wrapping native credential approval workflows and contextual linking."""

    def __init__(self, manager: NativeCredentialApprovalManager | None = None) -> None:
        self._manager = manager or NativeCredentialApprovalManager()

    def create_ask(self, req: CreateCredentialAskRequest) -> CredentialAskDto:
        """Create a new credential access approval request."""
        ask = self._manager.create_ask(
            credential_id=req.credential_id,
            service_name=req.service_name,
            account_label=req.account_label,
            requester_id=req.requester_id,
            owner_id=req.owner_id,
            purpose=req.purpose,
            session_id=req.session_id,
            message_id=req.message_id,
            sequence_number=req.sequence_number,
            turn_index=req.turn_index,
        )
        return _to_dto_ask(ask)

    def decide_ask(
        self, ask_id: str, req: DecideCredentialAskRequest
    ) -> DecideCredentialAskResponse:
        """Decide a pending credential approval request."""
        decision = ApprovalDecision(req.decision.lower())
        updated_ask, audit_record = self._manager.decide_ask(
            ask_id=ask_id,
            decider_id=req.decider_id,
            decision=decision,
            note=req.note,
        )
        return DecideCredentialAskResponse(
            ask=_to_dto_ask(updated_ask),
            audit_record=_to_dto_audit(audit_record),
        )

    def get_ask(self, ask_id: str) -> CredentialAskDto | None:
        """Retrieve a credential ask by ID."""
        ask = self._manager.get_ask(ask_id)
        if ask is None:
            return None
        return _to_dto_ask(ask)

    def list_pending_asks(self, owner_id: str | None = None) -> PendingAsksResponse:
        """List all pending asks, optionally filtered by owner."""
        pending = self._manager.list_pending_asks(owner_id=owner_id)
        dtos = [_to_dto_ask(a) for a in pending]
        return PendingAsksResponse(
            pending_asks=dtos,
            total_count=len(dtos),
        )

    def list_audit_records(self) -> list[ApprovalAuditRecordDto]:
        """List all historical credential approval audit records."""
        records = self._manager.get_audit_records()
        return [_to_dto_audit(r) for r in records]


_service_instance: NativeCredentialApprovalService | None = None


def get_native_credential_approval_service() -> NativeCredentialApprovalService:
    """FastAPI dependency provider for NativeCredentialApprovalService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = NativeCredentialApprovalService()
    return _service_instance
