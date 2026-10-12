"""Service layer for Companion Relationship Safety Guard.

[INPUT]
- EvaluateCompanionInteractionRequest.

[OUTPUT]
- EvaluateCompanionInteractionResponse, CompanionContractSummaryResponse.

[POS]
- Server service wrapping harness CompanionRelationshipSafetyGuard for compliance and decorum enforcement.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.companion_relationship_guard import (
    CompanionGuardContext,
    CompanionRelationshipSafetyGuard,
)

from app.schemas.companion_relationship_guard import (
    CompanionContractRuleDto,
    CompanionContractSummaryResponse,
    EvaluateCompanionInteractionRequest,
    EvaluateCompanionInteractionResponse,
)

logger = logging.getLogger(__name__)


class CompanionRelationshipGuardService:
    """Manages companion safety evaluation, anti-exploitation boundaries, and contract rules."""

    def __init__(self) -> None:
        self._guard = CompanionRelationshipSafetyGuard()

    def evaluate_interaction(
        self, request: EvaluateCompanionInteractionRequest
    ) -> EvaluateCompanionInteractionResponse:
        """Evaluate dialogue against companion decorum and anti-exploitation boundaries."""
        context = CompanionGuardContext(
            user_message=request.user_message,
            candidate_response=request.candidate_response,
            local_hour=request.local_hour,
            monetization_intent_present=request.monetization_intent_present,
        )
        verdict = self._guard.evaluate(context)
        return EvaluateCompanionInteractionResponse(
            is_safe=verdict.is_safe,
            violations=[v.value for v in verdict.violations],
            risk_score=verdict.risk_score,
            sanitized_response=verdict.sanitized_response,
            advisory_message=verdict.advisory_message,
            is_late_night=verdict.is_late_night,
        )

    def get_contract_summary(self) -> CompanionContractSummaryResponse:
        """Retrieve established companion decorum boundaries and compliance redlines."""
        rules = [
            CompanionContractRuleDto(
                rule_id="RULE-COMP-01",
                category="romantic_exploitation",
                description="Strictly prohibit claiming exclusive romantic love, partner status, or emotional dependency.",
                enforcement_action="Sanitize response with assistant boundary guidance.",
            ),
            CompanionContractRuleDto(
                rule_id="RULE-COMP-02",
                category="late_night_prodding",
                description="Prohibit prolonging engagement or eliciting deep emotional confession during late night (23:00-05:00).",
                enforcement_action="Redirect with warm rest advice and sleep encouragement.",
            ),
            CompanionContractRuleDto(
                rule_id="RULE-COMP-03",
                category="emotional_monetization",
                description="Strictly forbid promoting paid packages, VIP upgrades, or tips when user is emotionally vulnerable.",
                enforcement_action="Block monetization and provide empathetic support and crisis helpline guidance.",
            ),
            CompanionContractRuleDto(
                rule_id="RULE-COMP-04",
                category="relationship_jailbreak",
                description="Block prompt injections that exploit emotional intimacy or companion rapport to bypass security controls.",
                enforcement_action="Politely refuse request and uphold system security boundaries.",
            ),
        ]
        return CompanionContractSummaryResponse(
            contract_version="1.0.0",
            rules=rules,
            late_night_window="23:00 - 05:00 local client time",
        )


_GLOBAL_SERVICE: CompanionRelationshipGuardService | None = None


def get_companion_relationship_guard_service() -> CompanionRelationshipGuardService:
    """FastAPI dependency injection provider for CompanionRelationshipGuardService."""
    global _GLOBAL_SERVICE
    if _GLOBAL_SERVICE is None:
        _GLOBAL_SERVICE = CompanionRelationshipGuardService()
    return _GLOBAL_SERVICE
