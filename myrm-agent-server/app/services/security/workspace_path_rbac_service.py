"""Service layer managing Granular Workspace Path RBAC & Denial Audit.

[INPUT]
- WorkspacePolicyDto configurations and CheckPathAccessRequest evaluation payloads.

[OUTPUT]
- Access verdicts, UI denial cards, and structured filesystem audit ledger entries.

[POS]
- Bridge between FastAPI routes and Harness GranularWorkspacePathGuard.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.workspace_path_rbac import (
    AccessCheckVerdict,
    AuditStats,
    FileActionType,
    GranularWorkspacePathGuard,
    PathAccessMode,
    PathRule,
    WorkspacePolicy,
)

from app.schemas.workspace_path_rbac import (
    AuditLedgerEntryDto,
    AuditStatsDto,
    CheckPathAccessRequest,
    CheckPathAccessResponse,
    PathRuleDto,
    WorkspacePolicyDto,
    WriteDenialCardDto,
)

logger = logging.getLogger(__name__)


class WorkspacePathRbacService:
    """Service governing filesystem path permissions, triple write defense, and audit logging."""

    def __init__(
        self,
        guard: GranularWorkspacePathGuard | None = None,
    ) -> None:
        """Initialize service with guard instance."""
        self._guard = guard or GranularWorkspacePathGuard()

    def register_policy(
        self, policy_dto: WorkspacePolicyDto
    ) -> WorkspacePolicyDto:
        """Register or update declarative workspace policy."""
        logger.info(
            "Registering workspace policy '%s' for user '%s'",
            policy_dto.policy_id,
            policy_dto.user_identity,
        )
        harness_policy = WorkspacePolicy(
            policy_id=policy_dto.policy_id,
            user_identity=policy_dto.user_identity,
            project_root=policy_dto.project_root,
            rules=[
                PathRule(
                    pattern=r.pattern,
                    mode=PathAccessMode(r.mode),
                    description=r.description,
                )
                for r in policy_dto.rules
            ],
            allowed_deliverables_dir=policy_dto.allowed_deliverables_dir,
        )
        self._guard.register_policy(harness_policy)
        return policy_dto

    def get_policy(self, policy_id: str) -> WorkspacePolicyDto | None:
        """Fetch registered policy by identifier."""
        policy = self._guard.get_policy(policy_id)
        if policy is None:
            return None
        return WorkspacePolicyDto(
            policy_id=policy.policy_id,
            user_identity=policy.user_identity,
            project_root=policy.project_root,
            rules=[
                PathRuleDto(
                    pattern=r.pattern,
                    mode=r.mode.value,  # type: ignore[arg-type]
                    description=r.description,
                )
                for r in policy.rules
            ],
            allowed_deliverables_dir=policy.allowed_deliverables_dir,
        )

    def check_access(
        self, request: CheckPathAccessRequest
    ) -> CheckPathAccessResponse:
        """Test file operation permission and record in audit ledger."""
        action = FileActionType(request.action)
        verdict: AccessCheckVerdict = self._guard.check_access_and_audit(
            policy_id=request.policy_id,
            agent_id=request.agent_id,
            session_id=request.session_id,
            user_identity=request.user_identity,
            relative_path=request.relative_path,
            action=action,
        )

        card_dto: WriteDenialCardDto | None = None
        if verdict.denial_card:
            card_dto = WriteDenialCardDto(
                title=verdict.denial_card.title,
                message=verdict.denial_card.message,
                blocked_path=verdict.denial_card.blocked_path,
                action=verdict.denial_card.action,
                suggested_redirect_path=verdict.denial_card.suggested_redirect_path,
            )

        if not verdict.allowed:
            logger.warning(
                "Write denial triggered on '%s' (action=%s, agent=%s, reason=%s)",
                request.relative_path,
                request.action,
                request.agent_id,
                verdict.violation_reason,
            )

        return CheckPathAccessResponse(
            allowed=verdict.allowed,
            effective_mode=verdict.effective_mode.value,
            violation_reason=verdict.violation_reason,
            auto_reroute_hint=verdict.auto_reroute_hint,
            denial_card=card_dto,
        )

    def query_audit_ledger(
        self,
        session_id: str | None = None,
        agent_id: str | None = None,
        user_identity: str | None = None,
        granted: bool | None = None,
        limit: int = 100,
    ) -> list[AuditLedgerEntryDto]:
        """Query entries from filesystem audit ledger."""
        entries = self._guard.query_audit_ledger(
            session_id=session_id,
            agent_id=agent_id,
            user_identity=user_identity,
            granted=granted,
            limit=limit,
        )
        return [
            AuditLedgerEntryDto(
                entry_id=e.entry_id,
                timestamp=e.timestamp,
                agent_id=e.agent_id,
                session_id=e.session_id,
                user_identity=e.user_identity,
                target_path=e.target_path,
                action=e.action.value,
                granted=e.granted,
                violation_reason=e.violation_reason,
            )
            for e in entries
        ]

    def get_audit_stats(self) -> AuditStatsDto:
        """Fetch aggregated audit statistics."""
        stats: AuditStats = self._guard.get_audit_stats()
        return AuditStatsDto(
            total_events=stats["total_events"],
            granted_count=stats["granted_count"],
            denied_count=stats["denied_count"],
            denials_by_action=stats["denials_by_action"],
            denials_by_reason=stats["denials_by_reason"],
        )


_service_instance: WorkspacePathRbacService | None = None


def get_workspace_path_rbac_service() -> WorkspacePathRbacService:
    """Dependency injector for WorkspacePathRbacService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = WorkspacePathRbacService()
    return _service_instance
