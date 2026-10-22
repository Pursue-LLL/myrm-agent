"""Service implementing Conversational Multi-Specialist Summoning & Context Aggregation (Item 54).

[INPUT]
- SummonSpecialistRequest, DetectIntentRequest.

[OUTPUT]
- SpecialistProfileDTO, StructuredAggregationCardDTO, SummonSessionExecutionDTO,
  DetectIntentResponse.

[POS]
- Server-side business service wrapping the Harness SpecialistSummoningCoordinator engine.
"""

from __future__ import annotations

import uuid

from myrm_agent_harness.agent.sub_agents.specialist_summoning import (
    SpecialistProfile,
    SpecialistSummoningCoordinator,
    StructuredAggregationCard,
    SummonRequest,
    SummonSessionExecution,
    SummonTriggerSource,
)

from app.schemas.specialist_summoning import (
    AggregationCardTypeEnum,
    DetectIntentResponse,
    SpecialistDomainEnum,
    SpecialistProfileDTO,
    StructuredAggregationCardDTO,
    SummonExecutionStatusEnum,
    SummonSessionExecutionDTO,
    SummonSpecialistRequest,
    SummonTriggerSourceEnum,
)


def _convert_domain_profile_to_dto(profile: SpecialistProfile) -> SpecialistProfileDTO:
    """Convert domain SpecialistProfile to DTO."""
    return SpecialistProfileDTO(
        specialist_id=profile.specialist_id,
        name=profile.name,
        mention_tag=profile.mention_tag,
        domain=SpecialistDomainEnum(profile.domain.value),
        description=profile.description,
        system_prompt_addon=profile.system_prompt_addon,
        suggested_keywords=list(profile.suggested_keywords),
    )


def _convert_domain_card_to_dto(card: StructuredAggregationCard) -> StructuredAggregationCardDTO:
    """Convert domain StructuredAggregationCard to DTO."""
    return StructuredAggregationCardDTO(
        card_id=card.card_id,
        summon_id=card.summon_id,
        specialist_id=card.specialist_id,
        specialist_name=card.specialist_name,
        card_type=AggregationCardTypeEnum(card.card_type.value),
        headline=card.headline,
        deliverable_payload=card.deliverable_payload,
        artifacts=list(card.artifacts),
        created_at=card.created_at,
    )


def _convert_domain_execution_to_dto(execution: SummonSessionExecution) -> SummonSessionExecutionDTO:
    """Convert domain SummonSessionExecution to DTO."""
    card_dto = None
    if execution.aggregation_card:
        card_dto = _convert_domain_card_to_dto(execution.aggregation_card)

    return SummonSessionExecutionDTO(
        summon_id=execution.summon_id,
        chat_id=execution.chat_id,
        specialist_id=execution.specialist_id,
        status=SummonExecutionStatusEnum(execution.status.value),
        trigger_source=SummonTriggerSourceEnum(execution.request.trigger_source.value),
        instruction=execution.request.instruction,
        aggregation_card=card_dto,
        execution_seconds=execution.execution_seconds,
        error_message=execution.error_message,
    )


class SpecialistSummoningService:
    """Business service governing specialist summoning, intent sensing, and structured returns."""

    _instance: SpecialistSummoningService | None = None

    def __init__(self) -> None:
        """Initialize service with Harness coordinator and in-memory execution history."""
        self._coordinator = SpecialistSummoningCoordinator()
        self._executions_by_chat: dict[str, list[SummonSessionExecutionDTO]] = {}

    @classmethod
    def get_instance(cls) -> SpecialistSummoningService:
        """Retrieve singleton service instance."""
        if cls._instance is None:
            cls._instance = SpecialistSummoningService()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton service instance for test isolation."""
        cls._instance = None

    def get_catalog(self) -> list[SpecialistProfileDTO]:
        """Retrieve full catalog of available specialist profiles."""
        return [_convert_domain_profile_to_dto(p) for p in self._coordinator.get_catalog()]

    def get_specialist(self, specialist_id: str) -> SpecialistProfileDTO | None:
        """Retrieve a specialist by identifier."""
        profile = self._coordinator.get_specialist(specialist_id)
        if profile is None:
            return None
        return _convert_domain_profile_to_dto(profile)

    def detect_intent(self, message: str) -> DetectIntentResponse:
        """Scan input message for explicit @-mention or implicit intent keywords."""
        detection = self._coordinator.detect_mention_or_intent(message)
        if detection is None:
            return DetectIntentResponse(matched=False)

        profile, source, cleaned_instruction = detection
        return DetectIntentResponse(
            matched=True,
            specialist=_convert_domain_profile_to_dto(profile),
            trigger_source=SummonTriggerSourceEnum(source.value),
            cleaned_instruction=cleaned_instruction,
        )

    def summon_specialist(
        self, chat_id: str, request_dto: SummonSpecialistRequest
    ) -> SummonSessionExecutionDTO:
        """Dispatch a specialist invocation in an isolated sandbox session."""
        summon_id = f"summon-{uuid.uuid4().hex[:12]}"
        trigger_source = SummonTriggerSource(request_dto.trigger_source.value)

        domain_req = SummonRequest(
            summon_id=summon_id,
            chat_id=chat_id,
            specialist_id=request_dto.specialist_id,
            trigger_source=trigger_source,
            instruction=request_dto.instruction,
            parent_context_slice=request_dto.parent_context_slice,
        )

        domain_exec = self._coordinator.execute_isolated_specialist(domain_req)
        exec_dto = _convert_domain_execution_to_dto(domain_exec)

        if chat_id not in self._executions_by_chat:
            self._executions_by_chat[chat_id] = []
        self._executions_by_chat[chat_id].append(exec_dto)

        return exec_dto

    def get_session_executions(self, chat_id: str) -> list[SummonSessionExecutionDTO]:
        """Retrieve all recorded specialist executions and return cards for a chat session."""
        return list(self._executions_by_chat.get(chat_id, []))

    def clear_session_executions(self, chat_id: str) -> None:
        """Clear recorded executions for a session."""
        if chat_id in self._executions_by_chat:
            self._executions_by_chat.pop(chat_id, None)
