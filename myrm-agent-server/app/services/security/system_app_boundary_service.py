"""
[POS] app/services/security/system_app_boundary_service.py
[INPUT] app.schemas.system_app_boundary, myrm_agent_harness.core.security.system_app_boundary
[OUTPUT] SystemAppBoundaryService, get_system_app_boundary_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.system_app_boundary import (
    AppAccessRequest,
    AppOperationType,
    SystemAppBoundaryFacade,
    SystemAppScopeRule,
    SystemAppType,
)

from app.schemas.system_app_boundary import (
    AppAccessRequestDTO,
    AppAccessVerdictResponseDTO,
    GrantWriteConsentRequestDTO,
    RejectWriteConsentRequestDTO,
    SetScopeRuleRequestDTO,
    SystemAppAuditRecordResponseDTO,
    SystemAppBoundaryMetricsResponseDTO,
    SystemAppScopeRuleResponseDTO,
)

logger = logging.getLogger(__name__)


class SystemAppBoundaryService:
    """Service governing privacy boundaries and human consent gates for local system applications."""

    def __init__(
        self, facade: SystemAppBoundaryFacade | None = None
    ) -> None:
        self._facade = facade or SystemAppBoundaryFacade()

    def evaluate_access(
        self, request: AppAccessRequestDTO
    ) -> AppAccessVerdictResponseDTO:
        """Assert access request against declared container boundaries and mutation consent policies."""
        app_type = self._parse_app_type(request.app_type)
        op_type = self._parse_op_type(request.operation_type)

        req_domain = AppAccessRequest(
            request_id=request.request_id,
            session_id=request.session_id,
            app_type=app_type,
            operation_type=op_type,
            target_container=request.target_container,
            payload_summary=request.payload_summary,
            is_external_tainted=request.is_external_tainted,
        )
        verdict = self._facade.evaluate_access(req_domain)

        return AppAccessVerdictResponseDTO(
            request_id=verdict.request_id,
            decision=verdict.decision.value,
            is_allowed=verdict.is_allowed,
            diagnostic_reason=verdict.diagnostic_reason,
            audit_id=verdict.audit_id,
        )

    def grant_write_consent(
        self, request: GrantWriteConsentRequestDTO
    ) -> AppAccessVerdictResponseDTO | None:
        """Approve and grant one-time execution consent for a held write request."""
        verdict = self._facade.grant_write_consent(
            request_id=request.request_id, approver_note=request.approver_note
        )
        if verdict is None:
            return None
        return AppAccessVerdictResponseDTO(
            request_id=verdict.request_id,
            decision=verdict.decision.value,
            is_allowed=verdict.is_allowed,
            diagnostic_reason=verdict.diagnostic_reason,
            audit_id=verdict.audit_id,
        )

    def reject_write_consent(
        self, request: RejectWriteConsentRequestDTO
    ) -> bool:
        """Reject and drop a held write request."""
        return self._facade.reject_write_consent(
            request_id=request.request_id, reason=request.reason
        )

    def list_pending_consents(self) -> list[AppAccessRequestDTO]:
        """Fetch all requests currently held awaiting human consent."""
        pending = self._facade.list_pending_consents()
        return [
            AppAccessRequestDTO(
                request_id=p.request_id,
                session_id=p.session_id,
                app_type=p.app_type.value,
                operation_type=p.operation_type.value,
                target_container=p.target_container,
                payload_summary=p.payload_summary,
                is_external_tainted=p.is_external_tainted,
            )
            for p in pending
        ]

    def set_scope_rule(
        self, request: SetScopeRuleRequestDTO
    ) -> SystemAppScopeRuleResponseDTO:
        """Register or update container access boundaries for an application."""
        app_type = self._parse_app_type(request.app_type)
        rule = SystemAppScopeRule(
            app_type=app_type,
            allowed_containers=tuple(request.allowed_containers),
            allow_mutations_without_prompt=request.allow_mutations_without_prompt,
            is_locked_down=request.is_locked_down,
        )
        self._facade.set_scope_rule(rule)
        return self.get_scope_rule(request.app_type)

    def get_scope_rule(self, app_type_str: str) -> SystemAppScopeRuleResponseDTO:
        """Retrieve declared scoping rule for application."""
        app_type = self._parse_app_type(app_type_str)
        rule = self._facade.get_scope_rule(app_type)
        return SystemAppScopeRuleResponseDTO(
            app_type=rule.app_type.value,
            allowed_containers=list(rule.allowed_containers),
            allow_mutations_without_prompt=rule.allow_mutations_without_prompt,
            is_locked_down=rule.is_locked_down,
        )

    def lockdown_app(self, app_type_str: str) -> SystemAppScopeRuleResponseDTO:
        """Place an application under emergency lockdown."""
        app_type = self._parse_app_type(app_type_str)
        self._facade.lockdown_app(app_type)
        return self.get_scope_rule(app_type_str)

    def unlock_app(self, app_type_str: str) -> SystemAppScopeRuleResponseDTO:
        """Release emergency lockdown on application."""
        app_type = self._parse_app_type(app_type_str)
        self._facade.unlock_app(app_type)
        return self.get_scope_rule(app_type_str)

    def get_audit_trail(
        self, limit: int = 50
    ) -> list[SystemAppAuditRecordResponseDTO]:
        """Fetch chronological audit records."""
        records = self._facade.get_audit_trail(limit=limit)
        return [
            SystemAppAuditRecordResponseDTO(
                audit_id=r.audit_id,
                timestamp_epoch=r.timestamp_epoch,
                request_id=r.request_id,
                session_id=r.session_id,
                app_type=r.app_type.value,
                operation_type=r.operation_type.value,
                target_container=r.target_container,
                is_allowed=r.is_allowed,
                reason=r.reason,
            )
            for r in records
        ]

    def get_metrics(self) -> SystemAppBoundaryMetricsResponseDTO:
        """Fetch cumulative boundary access metrics."""
        m = self._facade.metrics
        return SystemAppBoundaryMetricsResponseDTO(
            requests_evaluated_total=m.requests_evaluated_total,
            silent_reads_permitted_total=m.silent_reads_permitted_total,
            write_consents_requested_total=m.write_consents_requested_total,
            write_consents_granted_total=m.write_consents_granted_total,
            boundary_violations_blocked_total=m.boundary_violations_blocked_total,
            lockdown_blocked_total=m.lockdown_blocked_total,
        )

    @staticmethod
    def _parse_app_type(raw: str) -> SystemAppType:
        try:
            return SystemAppType(raw.strip().upper())
        except ValueError:
            logger.warning("Unknown app type '%s', falling back to OTHER", raw)
            return SystemAppType.OTHER

    @staticmethod
    def _parse_op_type(raw: str) -> AppOperationType:
        try:
            return AppOperationType(raw.strip().upper())
        except ValueError:
            logger.warning("Unknown operation type '%s', defaulting to MUTATE_WRITE for safety", raw)
            return AppOperationType.MUTATE_WRITE


_global_service: SystemAppBoundaryService | None = None


def get_system_app_boundary_service() -> SystemAppBoundaryService:
    """Singleton provider for SystemAppBoundaryService."""
    global _global_service
    if _global_service is None:
        _global_service = SystemAppBoundaryService()
    return _global_service
