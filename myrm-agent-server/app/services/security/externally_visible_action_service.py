"""Service layer for Externally Visible Irreversible Action Static Classification Gate.

[INPUT]
- myrm_agent_harness.core.security.externally_visible_action::ExternallyVisibleActionGate
- app.schemas.externally_visible_action::*

[OUTPUT]
- ExternallyVisibleActionService, get_externally_visible_action_service

[POS]
Service coordinating action visibility classification, mandatory human review enforcement, and audit logs.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.externally_visible_action import (
    AuditedExternalAction,
    ExternalActionClassification,
    ExternallyVisibleActionGate,
)
from myrm_agent_harness.core.security.tool_registry.registry import SafetyMetadata

from app.schemas.externally_visible_action import (
    AuditedExternalActionResponse,
    AuditTrailResponse,
    EvaluateActionRequest,
    ExternalActionClassificationResponse,
    RecordExternalActionAuditRequest,
)

logger = logging.getLogger(__name__)


def _to_classification_response(
    classification: ExternalActionClassification,
) -> ExternalActionClassificationResponse:
    return ExternalActionClassificationResponse(
        tool_name=classification.tool_name,
        is_third_party_visible=classification.is_third_party_visible,
        requires_mandatory_human_review=classification.requires_mandatory_human_review,
        hide_allow_always=classification.hide_allow_always,
        visibility_scope=classification.visibility_scope.value,
        rationale=classification.rationale,
    )


def _to_audit_response(record: AuditedExternalAction) -> AuditedExternalActionResponse:
    return AuditedExternalActionResponse(
        action_id=record.action_id,
        session_id=record.session_id,
        agent_id=record.agent_id,
        tool_name=record.tool_name,
        recipient_or_destination=record.recipient_or_destination,
        content_preview=record.content_preview,
        is_approved=record.is_approved,
        approved_by=record.approved_by,
        timestamp=record.timestamp,
    )


class ExternallyVisibleActionService:
    """Business service governing action visibility evaluation and audit trails."""

    def __init__(self, gate: ExternallyVisibleActionGate | None = None) -> None:
        self._gate: ExternallyVisibleActionGate = gate or ExternallyVisibleActionGate()

    def evaluate_action(
        self,
        request: EvaluateActionRequest,
    ) -> ExternalActionClassificationResponse:
        """Evaluate visibility classification of a tool."""
        explicit_meta: SafetyMetadata | None = None
        if request.custom_is_third_party_visible is not None:
            explicit_meta = SafetyMetadata(is_third_party_visible=request.custom_is_third_party_visible)

        classification = self._gate.classify_tool(
            tool_name=request.tool_name,
            explicit_metadata=explicit_meta,
        )
        return _to_classification_response(classification)

    def record_audit(
        self,
        request: RecordExternalActionAuditRequest,
    ) -> AuditedExternalActionResponse:
        """Record an external action execution or review attempt."""
        record = self._gate.record_audit(
            action_id=request.action_id,
            session_id=request.session_id,
            agent_id=request.agent_id,
            tool_name=request.tool_name,
            recipient_or_destination=request.recipient_or_destination,
            content_preview=request.content_preview,
            is_approved=request.is_approved,
            approved_by=request.approved_by,
        )
        return _to_audit_response(record)

    def get_audit_trail(
        self,
        session_id: str | None = None,
        limit: int = 50,
    ) -> AuditTrailResponse:
        """Query external action audit log entries."""
        records = self._gate.get_audit_records(session_id=session_id, limit=limit)
        return AuditTrailResponse(
            records=[_to_audit_response(r) for r in records],
            total=len(records),
        )

    def clear_audit_records(self) -> None:
        """Clear audit history (used in test isolation)."""
        self._gate.clear_audit_records()


_INSTANCE: ExternallyVisibleActionService | None = None


def get_externally_visible_action_service() -> ExternallyVisibleActionService:
    """Return singleton instance of ExternallyVisibleActionService."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ExternallyVisibleActionService()
    return _INSTANCE
