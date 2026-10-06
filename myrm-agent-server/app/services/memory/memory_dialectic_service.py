"""
[POS] app/services/memory/memory_dialectic_service.py
[INPUT] app.schemas.memory_dialectic, myrm_agent_harness.toolkits.memory.dialectic
[OUTPUT] MemoryDialecticService, get_memory_dialectic_service

Service coordinating Dialectic Reasoning Engine, Cadence Governor, and Volatile Prompt Slices.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.dialectic import (
    DialecticCadenceConfig,
    DialecticCadenceGovernor,
    DialecticEphemeralMind,
    DialecticReasoningEngine,
    DialecticReasoningResult,
)

from app.schemas.memory_dialectic import (
    DialecticCadenceConfigDTO,
    DialecticCadenceStatusResponseDTO,
    DialecticEphemeralMindDTO,
    DialecticProcessTurnRequestDTO,
    DialecticReasoningResponseDTO,
)


def _to_dto_mind(mind: DialecticEphemeralMind | None) -> DialecticEphemeralMindDTO | None:
    """Convert harness DialecticEphemeralMind to DialecticEphemeralMindDTO."""
    if mind is None:
        return None
    return DialecticEphemeralMindDTO(
        conversation_id=mind.conversation_id,
        immediate_focus=mind.immediate_focus,
        resistance_points=list(mind.resistance_points),
        implicit_goals=list(mind.implicit_goals),
        confidence=mind.confidence,
        turn_index=mind.turn_index,
        updated_at=mind.updated_at,
    )


def _to_dto_reasoning_result(
    result: DialecticReasoningResult,
) -> DialecticReasoningResponseDTO:
    """Convert harness DialecticReasoningResult to DialecticReasoningResponseDTO."""
    return DialecticReasoningResponseDTO(
        conversation_id=result.conversation_id,
        turn_index=result.turn_index,
        is_throttled=result.is_throttled,
        heat_state=result.heat_state.value,
        base_profile_updated=result.base_profile_updated,
        ephemeral_mind_updated=result.ephemeral_mind_updated,
        ephemeral_mind=_to_dto_mind(result.ephemeral_mind),
        prompt_volatile_slice=result.prompt_volatile_slice,
        reasoning_summary=result.reasoning_summary,
    )


class MemoryDialecticService:
    """Service governing dialectic profile reasoning and adaptive context throttling."""

    def __init__(self, config_dto: DialecticCadenceConfigDTO | None = None) -> None:
        if config_dto is not None:
            config = DialecticCadenceConfig(
                base_profile_cadence_turns=config_dto.base_profile_cadence_turns,
                ephemeral_cadence_turns=config_dto.ephemeral_cadence_turns,
                cold_boot_threshold_turns=config_dto.cold_boot_threshold_turns,
                max_ephemeral_chars=config_dto.max_ephemeral_chars,
                enable_throttling=config_dto.enable_throttling,
            )
        else:
            config = DialecticCadenceConfig()

        self._governor = DialecticCadenceGovernor(config=config)
        self._engine = DialecticReasoningEngine(config=config, governor=self._governor)

    def process_turn(
        self, request: DialecticProcessTurnRequestDTO
    ) -> DialecticReasoningResponseDTO:
        """Process an interaction turn through dialectic reasoning and cadence throttling."""
        result = self._engine.process_turn(
            conversation_id=request.conversation_id,
            user_prompt=request.user_prompt,
            assistant_response=request.assistant_response,
            turn_index=request.turn_index,
        )
        return _to_dto_reasoning_result(result)

    def get_cadence_status(
        self, conversation_id: str
    ) -> DialecticCadenceStatusResponseDTO:
        """Retrieve live cadence status and heat state for a conversation."""
        current_turn = self._governor.get_turn(conversation_id)
        heat_state = self._governor.get_heat_state(conversation_id)
        should_extract = self._governor.should_extract_ephemeral(conversation_id)
        should_refresh_base = self._governor.should_refresh_base_profile(conversation_id)

        return DialecticCadenceStatusResponseDTO(
            conversation_id=conversation_id,
            current_turn=current_turn,
            heat_state=heat_state.value,
            should_extract_ephemeral=should_extract,
            should_refresh_base_profile=should_refresh_base,
        )

    def get_ephemeral_mind(
        self, conversation_id: str
    ) -> DialecticEphemeralMindDTO | None:
        """Retrieve the latest extracted ephemeral mind snapshot."""
        mind = self._engine.get_latest_mind(conversation_id)
        return _to_dto_mind(mind)

    def reset_session(self, conversation_id: str) -> None:
        """Reset cadence governor state for a target session."""
        self._governor.reset_session(conversation_id)


_memory_dialectic_service_instance: MemoryDialecticService | None = None


def get_memory_dialectic_service() -> MemoryDialecticService:
    """Singleton getter for MemoryDialecticService."""
    global _memory_dialectic_service_instance
    if _memory_dialectic_service_instance is None:
        _memory_dialectic_service_instance = MemoryDialecticService()
    return _memory_dialectic_service_instance
