"""Service orchestrating Scoped Time-Bounded Action Grants and Trust Budgets.

[INPUT]
Harness core security action grants, trust budget engines, and schemas.

[OUTPUT]
ActionGrantService, get_action_grant_service.

[POS]
Service layer orchestrating four-dimensional scoped action grants, consumption tokens, and agent trust budget limits.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.action_grants import (
    ActionGrantRecord,
    ActionGrantRegistry,
    GrantEvaluationResult,
    TrustBudgetEngine,
    TrustBudgetRecord,
)


class ActionGrantService:
    """Service wrapping ActionGrantRegistry and TrustBudgetEngine."""

    def __init__(self, suggestion_threshold: int = 3) -> None:
        self._registry = ActionGrantRegistry()
        self._budget_engine = TrustBudgetEngine(
            default_suggestion_threshold=suggestion_threshold
        )

    @property
    def registry(self) -> ActionGrantRegistry:
        """Access underlying ActionGrantRegistry."""
        return self._registry

    @property
    def budget_engine(self) -> TrustBudgetEngine:
        """Access underlying TrustBudgetEngine."""
        return self._budget_engine

    def create_grant(
        self,
        agent_id: str,
        service: str,
        action: str,
        transaction: str = "*",
        ttl_seconds: float = 3600.0,
        max_uses: int | None = None,
    ) -> ActionGrantRecord:
        """Issue a new scoped 4D action grant."""
        return self._registry.create_grant(
            agent_id=agent_id,
            service=service,
            action=action,
            transaction=transaction,
            ttl_seconds=ttl_seconds,
            max_uses=max_uses,
        )

    def evaluate_action(
        self,
        agent_id: str,
        service: str,
        action: str,
        transaction: str,
    ) -> tuple[GrantEvaluationResult, ActionGrantRecord | None]:
        """Test action invocation against active grants."""
        return self._registry.evaluate_action(
            agent_id=agent_id,
            service=service,
            action=action,
            transaction=transaction,
        )

    def get_grant(self, grant_id: str) -> ActionGrantRecord | None:
        """Retrieve grant by identifier."""
        return self._registry.get_grant(grant_id)

    def revoke_grant(
        self,
        grant_id: str,
        reason: str = "Explicit user revocation",
    ) -> bool:
        """Monotonically revoke a single grant."""
        return self._registry.revoke_grant(grant_id=grant_id, reason=reason)

    def cascade_reclaim(
        self,
        service: str | None = None,
        agent_id: str | None = None,
        reason: str = "Cascade reclamation triggered",
    ) -> int:
        """Cascade revoke grants matching connector service or agent ID."""
        if service is not None:
            return self._registry.cascade_reclaim_by_service(service, reason=reason)
        if agent_id is not None:
            return self._registry.cascade_reclaim_by_agent(agent_id, reason=reason)
        return self._registry.revoke_all(reason=reason)

    def get_active_grants(
        self,
        agent_id: str | None = None,
        service: str | None = None,
    ) -> list[ActionGrantRecord]:
        """List all valid, unrevoked, and unexpired grants."""
        return self._registry.get_active_grants(agent_id=agent_id, service=service)

    def record_approval(
        self,
        agent_id: str,
        service: str,
        action: str,
    ) -> TrustBudgetRecord:
        """Record successful uncorrected user approval."""
        return self._budget_engine.record_approval(
            agent_id=agent_id,
            service=service,
            action=action,
        )

    def record_demotion(
        self,
        agent_id: str,
        service: str,
        action: str,
        reason: str = "User corrected or revoked action",
    ) -> TrustBudgetRecord:
        """Collapse trust budget to zero and lock back to Ask state."""
        return self._budget_engine.record_demotion(
            agent_id=agent_id,
            service=service,
            action=action,
            reason=reason,
        )

    def get_trust_budget(
        self,
        agent_id: str,
        service: str,
        action: str,
    ) -> TrustBudgetRecord:
        """Get current trust budget record."""
        return self._budget_engine.get_budget(
            agent_id=agent_id,
            service=service,
            action=action,
        )

    def should_suggest_grant(
        self,
        agent_id: str,
        service: str,
        action: str,
    ) -> bool:
        """Check if repeated approval warrants proactive grant creation."""
        return self._budget_engine.should_suggest_grant(
            agent_id=agent_id,
            service=service,
            action=action,
        )


_singleton_action_grant_service: ActionGrantService | None = None


def get_action_grant_service() -> ActionGrantService:
    """Retrieve or initialize singleton ActionGrantService."""
    global _singleton_action_grant_service
    if _singleton_action_grant_service is None:
        _singleton_action_grant_service = ActionGrantService()
    return _singleton_action_grant_service
