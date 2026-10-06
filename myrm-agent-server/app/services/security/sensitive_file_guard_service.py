"""Service layer for Sensitive Vault and Credential File Overwrite Deny Guard.

[INPUT]
- Harness SensitiveVaultAndCredentialFileOverwriteDenyGuard and schema request DTOs.

[OUTPUT]
- SensitiveFileGuardService managing file mutation inspections and temporary unlock grants.

[POS]
Service layer bridging HTTP presentation with harness sensitive vault and credential file protection.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.sensitive_file_guard import (
    FileWriteOperationType,
    SensitiveFileInspection,
    SensitiveVaultAndCredentialFileOverwriteDenyGuard,
)

from app.schemas.sensitive_file_guard import (
    FileUnlockGrantResponse,
    InspectFileOperationRequest,
    InspectFileOperationResponse,
    IssueUnlockGrantRequest,
    SensitiveFileAlertResponse,
)

logger = logging.getLogger(__name__)


class SensitiveFileGuardService:
    """Manages sensitive file protection rules, unlock tokens, and audit alerts."""

    def __init__(
        self, guard: SensitiveVaultAndCredentialFileOverwriteDenyGuard | None = None
    ) -> None:
        self.guard = guard or SensitiveVaultAndCredentialFileOverwriteDenyGuard()

    def inspect_file_operation(
        self, req: InspectFileOperationRequest
    ) -> InspectFileOperationResponse:
        """Evaluate whether a file mutation operation targets a protected sensitive file."""
        op_type = FileWriteOperationType(req.operation_type.lower())
        inspection = SensitiveFileInspection(
            target_path=req.target_path,
            operation_type=op_type,
            tool_name=req.tool_name,
            session_id=req.session_id,
            unlock_token=req.unlock_token,
        )
        decision = self.guard.inspect_file_operation(inspection)
        return InspectFileOperationResponse(
            allowed=decision.allowed,
            matched_rule_id=decision.matched_rule.rule_id if decision.matched_rule else None,
            category=decision.matched_rule.category.value if decision.matched_rule else None,
            reason=decision.reason,
            is_unlocked=decision.is_unlocked,
        )

    def issue_unlock_grant(
        self, req: IssueUnlockGrantRequest
    ) -> FileUnlockGrantResponse:
        """Issue an explicit temporary unlock token granting write access to a sensitive file."""
        grant = self.guard.unlock_manager.issue_grant(
            target_path=req.target_path,
            ttl_seconds=req.ttl_seconds,
            granted_by=req.granted_by,
        )
        return FileUnlockGrantResponse(
            canonical_path=grant.canonical_path,
            unlock_token=grant.unlock_token,
            expires_at=grant.expires_at,
            granted_by=grant.granted_by,
        )

    def revoke_unlock_grant(self, token: str) -> bool:
        """Revoke an active unlock authorization token."""
        return self.guard.unlock_manager.revoke_grant(token)

    def list_active_grants(self) -> list[FileUnlockGrantResponse]:
        """List active unexpired unlock grants."""
        grants = self.guard.unlock_manager.list_active_grants()
        return [
            FileUnlockGrantResponse(
                canonical_path=g.canonical_path,
                unlock_token=g.unlock_token,
                expires_at=g.expires_at,
                granted_by=g.granted_by,
            )
            for g in grants
        ]

    def get_alerts(
        self, session_id: str | None = None
    ) -> list[SensitiveFileAlertResponse]:
        """Retrieve security audit alerts for blocked file operations."""
        alerts = self.guard.get_alerts(session_id)
        return [
            SensitiveFileAlertResponse(
                alert_id=a.alert_id,
                session_id=a.session_id,
                target_path=a.target_path,
                category=a.category.value,
                operation_type=a.operation_type.value,
                tool_name=a.tool_name,
                reason=a.reason,
                timestamp=a.timestamp,
            )
            for a in alerts
        ]

    def clear_alerts(self) -> None:
        """Clear all logged alerts."""
        self.guard.clear_alerts()


_singleton_service: SensitiveFileGuardService | None = None


def get_sensitive_file_guard_service() -> SensitiveFileGuardService:
    """Retrieve singleton instance of SensitiveFileGuardService."""
    global _singleton_service
    if _singleton_service is None:
        _singleton_service = SensitiveFileGuardService()
    return _singleton_service
