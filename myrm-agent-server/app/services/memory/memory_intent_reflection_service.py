"""
[POS] app/services/memory/memory_intent_reflection_service.py
[INPUT] app.schemas.memory_intent_reflection, myrm_agent_harness.toolkits.memory.intent_reflection, myrm_agent_harness.toolkits.memory.types.ProceduralMemory
[OUTPUT] MemoryIntentReflectionService, get_memory_intent_reflection_service

Singleton service coordinating lightweight reflection intent classification and playbook activation probe.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.intent_reflection import (
    IntentClassificationResult,
    IntentLevelClassifier,
    PlaybookActivationDecision,
    PlaybookActivationProbe,
)
from myrm_agent_harness.toolkits.memory.types import ProceduralMemory

from app.schemas.memory_intent_reflection import (
    CandidateRuleDTO,
    ClassifyIntentRequestDTO,
    ClassifyIntentResponseDTO,
    EvaluateActivationRequestDTO,
    EvaluateActivationResponseDTO,
)


def _to_procedural_memory(dto: CandidateRuleDTO) -> ProceduralMemory:
    """Convert API CandidateRuleDTO into harness ProceduralMemory instance."""
    return ProceduralMemory(
        id=dto.id,
        user_id="default_user",
        trigger=dto.trigger or "when requested",
        action=dto.action or "execute",
        facets=list(dto.facets),
        is_active=dto.is_active,
        lifecycle_state=dto.lifecycle_state,
    )


class MemoryIntentReflectionService:
    """Service providing fast-path intent classification and selective playbook activation gating."""

    def __init__(
        self,
        classifier: IntentLevelClassifier | None = None,
        probe: PlaybookActivationProbe | None = None,
    ) -> None:
        self._classifier = classifier or IntentLevelClassifier()
        self._probe = probe or PlaybookActivationProbe(classifier=self._classifier)

    def classify_intent(
        self, request: ClassifyIntentRequestDTO
    ) -> ClassifyIntentResponseDTO:
        """Classify user query into operational intent tier with suggested facets."""
        res: IntentClassificationResult = self._classifier.classify(
            query=request.query,
            context=request.context_metadata,
        )
        return ClassifyIntentResponseDTO(
            tier=res.tier.value,
            confidence=res.confidence,
            matched_keywords=list(res.matched_keywords),
            suggested_facets=list(res.suggested_facets),
            source=res.source,
            reason=res.reason,
        )

    def evaluate_activation(
        self, request: EvaluateActivationRequestDTO
    ) -> EvaluateActivationResponseDTO:
        """Evaluate query and return activation decision against candidate rules."""
        harness_candidates = [
            _to_procedural_memory(dto) for dto in request.candidates
        ]
        decision: PlaybookActivationDecision = self._probe.evaluate(
            query=request.query,
            candidates=harness_candidates,
            context=request.context_metadata,
        )
        activated_ids = [rule.id for rule in decision.activated_rules]
        return EvaluateActivationResponseDTO(
            tier=decision.tier.value,
            bypass_retrieval=decision.bypass_retrieval,
            active_facets=list(decision.active_facets),
            activated_rule_ids=activated_ids,
            suppressed_rules_count=decision.suppressed_rules_count,
            decision_reason=decision.decision_reason,
        )


_service_instance: MemoryIntentReflectionService | None = None


def get_memory_intent_reflection_service() -> MemoryIntentReflectionService:
    """Acquire the singleton instance of MemoryIntentReflectionService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = MemoryIntentReflectionService()
    return _service_instance
