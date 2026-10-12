"""Service layer for LLM Egress Default-Deny & Credential Binding.

[INPUT]
- SetLlmEgressPolicyRequest, EvaluateLlmEgressRequest DTOs.

[OUTPUT]
- LlmEgressPolicyDto, LlmEgressVerdictDto.

[POS]
- Server service wrapping harness LlmEgressGuard.
"""

from __future__ import annotations

import time

from myrm_agent_harness.core.security.llm_egress_guard.guard import (
    LlmEgressGuard,
)
from myrm_agent_harness.core.security.llm_egress_guard.types import (
    DomainAllowlistRule,
    LlmEgressPolicy,
)

from app.schemas.llm_egress_guard import (
    DomainAllowlistRuleDto,
    EvaluateLlmEgressRequest,
    LlmEgressPolicyDto,
    LlmEgressVerdictDto,
    SetLlmEgressPolicyRequest,
)


class LlmEgressGuardService:
    """Coordinates policy lifecycle and outbound network egress validation."""

    def __init__(self, guard: LlmEgressGuard | None = None) -> None:
        self._guard = guard or LlmEgressGuard()

    def set_policy(
        self, request: SetLlmEgressPolicyRequest
    ) -> LlmEgressPolicyDto:
        """Install or update active LLM egress policy."""
        domain_rules: list[DomainAllowlistRule] = [
            DomainAllowlistRule(
                rule_id=r.rule_id,
                domain_pattern=r.domain_pattern,
                bound_credential_ids=tuple(r.bound_credential_ids),
                description=r.description,
                require_credential_binding=r.require_credential_binding,
            )
            for r in request.allowed_rules
        ]

        policy = LlmEgressPolicy(
            policy_id=request.policy_id,
            allowed_rules=tuple(domain_rules),
            is_default_deny=request.is_default_deny,
            enforced_at=time.time(),
        )

        self._guard.set_policy(policy)

        return LlmEgressPolicyDto(
            policy_id=policy.policy_id,
            allowed_rules=[
                DomainAllowlistRuleDto(
                    rule_id=r.rule_id,
                    domain_pattern=r.domain_pattern,
                    bound_credential_ids=list(r.bound_credential_ids),
                    description=r.description,
                    require_credential_binding=r.require_credential_binding,
                )
                for r in policy.allowed_rules
            ],
            is_default_deny=policy.is_default_deny,
            enforced_at=policy.enforced_at,
        )

    def get_policy(self) -> LlmEgressPolicyDto | None:
        """Retrieve the currently installed egress policy."""
        policy = self._guard.get_policy()
        if policy is None:
            return None

        return LlmEgressPolicyDto(
            policy_id=policy.policy_id,
            allowed_rules=[
                DomainAllowlistRuleDto(
                    rule_id=r.rule_id,
                    domain_pattern=r.domain_pattern,
                    bound_credential_ids=list(r.bound_credential_ids),
                    description=r.description,
                    require_credential_binding=r.require_credential_binding,
                )
                for r in policy.allowed_rules
            ],
            is_default_deny=policy.is_default_deny,
            enforced_at=policy.enforced_at,
        )

    def clear_policy(self) -> None:
        """Clear active policy, immediately reverting guard to fail-closed state."""
        self._guard.clear_policy()

    def evaluate_egress(
        self, request: EvaluateLlmEgressRequest
    ) -> LlmEgressVerdictDto:
        """Evaluate an outbound destination and presented credentials."""
        verdict = self._guard.evaluate_egress(
            target_url_or_domain=request.target_url_or_domain,
            presented_credential_id=request.presented_credential_id,
        )

        return LlmEgressVerdictDto(
            verdict=verdict.verdict.value,
            is_permitted=verdict.is_permitted,
            domain=verdict.domain,
            matched_rule_id=verdict.matched_rule_id,
            bound_credential_id=verdict.bound_credential_id,
            audit_id=verdict.audit_id,
            rationale=verdict.rationale,
        )


_default_service: LlmEgressGuardService | None = None


def get_llm_egress_guard_service() -> LlmEgressGuardService:
    """Singleton provider for LlmEgressGuardService."""
    global _default_service
    if _default_service is None:
        _default_service = LlmEgressGuardService()
    return _default_service
