"""
[POS] app/services/memory/memory_override_stack_service.py
[INPUT] app.schemas.memory_override_stack, myrm_agent_harness.toolkits.memory.override_stack, myrm_agent_harness.toolkits.memory.types.ProceduralMemory
[OUTPUT] MemoryOverrideStackService, get_memory_override_stack_service

Singleton service coordinating dynamic user override stack resolution and ephemeral bypass gating.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.override_stack import (
    DynamicUserOverrideStack,
    EphemeralBypassGate,
    EphemeralBypassRecord,
    PlaybookOverrideEvaluation,
)
from myrm_agent_harness.toolkits.memory.types import ProceduralMemory

from app.schemas.memory_override_stack import (
    EphemeralBypassRecordDTO,
    EvaluateOverrideStackRequestDTO,
    EvaluateOverrideStackResponseDTO,
    OverrideCandidateRuleDTO,
)


def _to_procedural_rule(dto: OverrideCandidateRuleDTO) -> ProceduralMemory:
    """Convert API OverrideCandidateRuleDTO to harness ProceduralMemory instance."""
    return ProceduralMemory(
        id=dto.id,
        user_id="default_user",
        trigger=dto.trigger or "when matching",
        action=dto.action,
        content=dto.content,
        facets=list(dto.facets),
        is_active=dto.is_active,
    )


def _to_bypass_record_dto(
    record: EphemeralBypassRecord,
) -> EphemeralBypassRecordDTO:
    """Convert harness EphemeralBypassRecord to API DTO."""
    return EphemeralBypassRecordDTO(
        rule_id=record.rule_id,
        rule_action=record.rule_action,
        conflicting_clause=record.conflicting_clause,
        bypass_reason=record.bypass_reason,
        bypassed_in_current_turn=record.bypassed_in_current_turn,
    )


class MemoryOverrideStackService:
    """Service providing 3-level priority stack resolution and ephemeral rule bypass gating."""

    def __init__(
        self,
        gate: EphemeralBypassGate | None = None,
        stack: DynamicUserOverrideStack | None = None,
    ) -> None:
        self._gate = gate or EphemeralBypassGate()
        self._stack = stack or DynamicUserOverrideStack(gate=self._gate)

    def resolve_override_stack(
        self, request: EvaluateOverrideStackRequestDTO
    ) -> EvaluateOverrideStackResponseDTO:
        """Resolve override stack enforcing Level 1 user prompt primacy over candidate rules."""
        rules = [_to_procedural_rule(dto) for dto in request.candidate_rules]
        evaluation: PlaybookOverrideEvaluation = self._stack.resolve(
            turn_prompt=request.turn_prompt,
            rules=rules,
            session_decisions=request.session_decisions,
        )

        active_ids = [rule.id for rule in evaluation.active_rules]
        bypassed_dtos = [
            _to_bypass_record_dto(r) for r in evaluation.bypassed_records
        ]

        return EvaluateOverrideStackResponseDTO(
            active_rule_ids=active_ids,
            bypassed_records=bypassed_dtos,
            injected_context_note=evaluation.injected_context_note,
            has_conflicts=evaluation.has_conflicts,
        )


_override_service_instance: MemoryOverrideStackService | None = None


def get_memory_override_stack_service() -> MemoryOverrideStackService:
    """Acquire the singleton instance of MemoryOverrideStackService."""
    global _override_service_instance
    if _override_service_instance is None:
        _override_service_instance = MemoryOverrideStackService()
    return _override_service_instance
