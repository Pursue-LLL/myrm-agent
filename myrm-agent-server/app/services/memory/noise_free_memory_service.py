"""Service layer for Tool-Noise-Free Memory Extraction and Purge Generation Epoch Suite.

[INPUT]
- Harness: myrm_agent_harness.toolkits.memory.noise_free_extractor
- Server DTOs: app.schemas.noise_free_memory

[OUTPUT]
- NoiseFreeMemoryService: Singleton service for noise stripping, PII gateway, and epoch fencing.

[POS]
Topic 01 Item 88 business logic layer (Anthropic Commerce Agents-style memory isolation and monotonic epoch fencing).
"""

from myrm_agent_harness.toolkits.memory import (
    ConversationTurn as HarnessConversationTurn,
)
from myrm_agent_harness.toolkits.memory import (
    ExtractedFactCandidate as HarnessFactCandidate,
)
from myrm_agent_harness.toolkits.memory import (
    NoiseFreeAsyncMemoryExtractor,
    NoiseFreeConfig,
    PIISafetyGateway,
)

from app.schemas.noise_free_memory import (
    CleanDialogueRequestDTO,
    CleanDialogueResponseDTO,
    CommitFactRequestDTO,
    CommitFactResponseDTO,
    EpochStatusResponseDTO,
    ExtractedFactCandidateDTO,
    InspectPIIRequestDTO,
    InspectPIIResponseDTO,
    PIIViolationDetailDTO,
    PurgeMemoryRequestDTO,
    PurgeMemoryResponseDTO,
)


class NoiseFreeMemoryService:
    """Singleton service bridging Harness NoiseFreeAsyncMemoryExtractor to server API."""

    def __init__(self) -> None:
        self._extractor = NoiseFreeAsyncMemoryExtractor(
            config=NoiseFreeConfig(
                strip_tool_receipts=True,
                enforce_pii_gate=True,
                mask_pii_instead_of_reject=False,
                min_confidence_threshold=0.75,
            )
        )
        self._pii_gateway = PIISafetyGateway()

    def prepare_clean_dialogue(
        self, request: CleanDialogueRequestDTO
    ) -> CleanDialogueResponseDTO:
        """Strip external tools and return noise-free transcript with observed generation epoch."""
        harness_turns = [
            HarnessConversationTurn(
                role=t.role,
                content=t.content,
                tool_calls=t.tool_calls,
                tool_call_id=t.tool_call_id,
            )
            for t in request.turns
        ]

        clean_transcript, observed_gen, tokens_saved = (
            self._extractor.prepare_clean_context(request.user_id, harness_turns)
        )

        stripped_count = sum(
            1 for t in request.turns if t.role == "tool" or t.tool_call_id is not None
        )

        return CleanDialogueResponseDTO(
            user_id=request.user_id,
            clean_transcript=clean_transcript,
            observed_generation=observed_gen,
            tokens_saved=tokens_saved,
            stripped_turns_count=stripped_count,
        )

    def inspect_pii_statement(
        self, request: InspectPIIRequestDTO
    ) -> InspectPIIResponseDTO:
        """Inspect statement using PII regular expression screening gateway."""
        gateway = (
            PIISafetyGateway(mask_instead_of_reject=True)
            if request.mask_instead_of_reject
            else self._pii_gateway
        )
        result = gateway.inspect(request.statement)

        violation_dtos = [
            PIIViolationDetailDTO(
                rule_name=v.rule_name,
                snippet_masked=v.snippet_masked,
                severity=v.severity,
            )
            for v in result.violations
        ]

        return InspectPIIResponseDTO(
            is_clean=result.is_clean,
            sanitized_text=result.sanitized_text,
            violations=violation_dtos,
        )

    def commit_extracted_fact(
        self, request: CommitFactRequestDTO
    ) -> CommitFactResponseDTO:
        """Validate candidate fact against monotonic generation epoch fence and PII gate."""
        candidate = HarnessFactCandidate(
            fact_id=request.candidate.fact_id,
            fact_text=request.candidate.fact_text,
            category=request.candidate.category,
            confidence=request.candidate.confidence,
            generation_observed=request.candidate.generation_observed,
            timestamp=request.candidate.timestamp.isoformat(),
        )

        success, message, primary_violation = (
            self._extractor.commit_extracted_fact(request.user_id, candidate)
        )

        violation_dto = (
            PIIViolationDetailDTO(
                rule_name=primary_violation.rule_name,
                snippet_masked=primary_violation.snippet_masked,
                severity=primary_violation.severity,
            )
            if primary_violation
            else None
        )

        return CommitFactResponseDTO(
            success=success,
            message=message,
            violation=violation_dto,
        )

    def purge_user_memory(
        self, request: PurgeMemoryRequestDTO
    ) -> PurgeMemoryResponseDTO:
        """Atomically clear memory and advance generation epoch to prevent stale async resurrection."""
        existing_facts = self._extractor.get_user_facts(request.user_id)
        count_purged = len(existing_facts)
        new_generation = self._extractor.purge_user_memory(request.user_id)

        return PurgeMemoryResponseDTO(
            user_id=request.user_id,
            new_generation=new_generation,
            purged_facts_count=count_purged,
        )

    def get_epoch_status(self, user_id: str) -> EpochStatusResponseDTO:
        """Retrieve epoch fence health, active tasks, and dropped stale write statistics."""
        status = self._extractor.get_epoch_status(user_id)
        return EpochStatusResponseDTO(
            user_id=status.user_id,
            current_generation=status.current_generation,
            active_extractions=status.active_extractions,
            stale_writes_dropped=status.stale_writes_dropped,
            last_purged_at=status.last_purged_at,
            stored_facts_count=status.stored_facts_count,
            pii_violations_blocked=status.pii_violations_blocked,
        )

    def get_user_facts(self, user_id: str) -> list[ExtractedFactCandidateDTO]:
        """Retrieve all currently committed memory facts for user."""
        facts = self._extractor.get_user_facts(user_id)
        return [
            ExtractedFactCandidateDTO(
                fact_id=f.fact_id,
                fact_text=f.fact_text,
                category=f.category,
                confidence=f.confidence,
                generation_observed=f.generation_observed,
            )
            for f in facts
        ]


_service_instance: NoiseFreeMemoryService | None = None


def get_noise_free_memory_service() -> NoiseFreeMemoryService:
    """Get or instantiate the singleton NoiseFreeMemoryService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = NoiseFreeMemoryService()
    return _service_instance
