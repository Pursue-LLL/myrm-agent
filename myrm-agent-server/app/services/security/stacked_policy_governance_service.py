"""Service managing Three-Tier Stacked Policy Governance and Tokenomics Downgrade Gate.

[INPUT]
- myrm_agent_harness.core.security.stacked_policy_governance::ThreeTierStackedPolicyStack, DowngradeGate

[OUTPUT]
- StackedPolicyGovernanceService, get_stacked_policy_governance_service

[POS]
Business service coordinating session/agent/server stacked policy evaluation and downgrade gate.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.stacked_policy_governance import (
    DowngradeGate,
    DowngradeGateSpec,
    DowngradeGateStatus,
    LifecyclePhase,
    PolicyEvaluationResult,
    PolicyRule,
    ThreeTierStackedPolicyStack,
)


class StackedPolicyGovernanceService:
    """Coordinates Session -> Agent -> Server stacked policy evaluation

    and tokenomics downgrade gating.
    """

    def __init__(self, downgrade_spec: DowngradeGateSpec | None = None) -> None:
        self._stack = ThreeTierStackedPolicyStack()
        self._gate = DowngradeGate(spec=downgrade_spec)
        self._seed_server_baseline_rules()

    def _seed_server_baseline_rules(self) -> None:
        """Seed organization-wide baseline security policies."""
        self._stack.add_server_rule(
            PolicyRule(
                tier="server",
                name="server_deny_destructive_rm",
                phase="tool_call",
                action="deny",
                target_pattern="rm -rf *",
                reason="Enterprise baseline blocks recursive root/directory deletion",
            )
        )
        self._stack.add_server_rule(
            PolicyRule(
                tier="server",
                name="server_deny_mkfs",
                phase="tool_call",
                action="deny",
                target_pattern="mkfs*",
                reason="Enterprise baseline blocks filesystem format commands",
            )
        )
        self._stack.add_server_rule(
            PolicyRule(
                tier="server",
                name="server_ask_shell_exec",
                phase="tool_call",
                action="ask",
                target_pattern="shell_exec",
                reason="Arbitrary shell execution requires interactive verification",
            )
        )

    def add_server_rule(self, rule: PolicyRule) -> None:
        """Register custom server baseline rule."""
        self._stack.add_server_rule(rule)

    def add_agent_rule(self, rule: PolicyRule) -> None:
        """Register agent-tier specification rule."""
        self._stack.add_agent_rule(rule)

    def add_session_rule(self, rule: PolicyRule) -> None:
        """Register dynamic session-tier user rule."""
        self._stack.add_session_rule(rule)

    def clear_session_rules(self, session_id: str) -> None:
        """Clear dynamic session rules upon session termination."""
        self._stack.clear_session_rules(session_id)

    def evaluate(
        self,
        phase: LifecyclePhase,
        target: str,
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> PolicyEvaluationResult:
        """Evaluate operation against stacked tiers."""
        return self._stack.evaluate(
            phase=phase,
            target=target,
            session_id=session_id,
            agent_id=agent_id,
        )

    def record_usage_and_check(
        self,
        session_id: str,
        additional_tokens: int,
        additional_cost: float,
    ) -> DowngradeGateStatus:
        """Record consumption and check if downgrade gate triggered."""
        return self._gate.record_usage(
            session_id=session_id,
            additional_tokens=additional_tokens,
            additional_cost=additional_cost,
        )

    def get_downgrade_status(self, session_id: str) -> DowngradeGateStatus:
        """Query downgrade status for a session."""
        return self._gate.get_status(session_id)

    def reset_session_budget(self, session_id: str) -> None:
        """Reset budget consumption counters."""
        self._gate.reset_session(session_id)


_singleton_governance_service: StackedPolicyGovernanceService | None = None


def get_stacked_policy_governance_service() -> StackedPolicyGovernanceService:
    """Retrieve or initialize singleton StackedPolicyGovernanceService."""
    global _singleton_governance_service
    if _singleton_governance_service is None:
        _singleton_governance_service = StackedPolicyGovernanceService()
    return _singleton_governance_service
