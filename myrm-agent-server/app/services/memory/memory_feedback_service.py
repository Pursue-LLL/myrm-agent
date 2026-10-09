"""Memory feedback service orchestrating live natural language corrections in server.

[INPUT]
- app.schemas.memory_feedback
- myrm_agent_harness.toolkits.memory (top-level export)

[OUTPUT]
- MemoryFeedbackService: Domain singleton for live correction operations.

[POS]
app.services.memory.memory_feedback_service
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    CorrectionAckReceipt,
    CorrectionSlot,
    LiveCorrectionOrchestrator,
    NaturalLanguageCorrectionDetector,
    TargetNodeCandidate,
)

from app.schemas.memory_feedback import (
    CorrectionDetectResponse,
    LiveCorrectionExecuteResponse,
    MutationResultDTO,
    TargetCandidateDTO,
)


class MemoryFeedbackService:
    """Service providing natural language feedback detection and live correction capabilities."""

    def __init__(self, orchestrator: LiveCorrectionOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator or LiveCorrectionOrchestrator()
        self._detector = NaturalLanguageCorrectionDetector()

    def detect_intent(self, utterance: str) -> CorrectionDetectResponse:
        """Scan utterance for correction intent and extract slot payload."""
        slot: CorrectionSlot | None = self._detector.detect(utterance)
        if slot is None:
            return CorrectionDetectResponse(
                detected=False,
                intent=None,
                corrected_value=None,
                negated_value=None,
                subject=None,
                confidence=0.0,
            )

        return CorrectionDetectResponse(
            detected=True,
            intent=str(slot.intent.value),
            corrected_value=slot.corrected_value,
            negated_value=slot.negated_value,
            subject=slot.subject,
            confidence=slot.confidence,
        )

    def execute_live_correction(
        self,
        utterance: str,
        candidates: list[TargetCandidateDTO],
    ) -> LiveCorrectionExecuteResponse:
        """Perform end-to-end live memory correction and generate user acknowledgement."""
        harness_candidates = [
            TargetNodeCandidate(
                memory_id=c.memory_id,
                content=c.content,
                cube_id=c.cube_id,
                match_score=c.match_score,
            )
            for c in candidates
        ]

        receipt: CorrectionAckReceipt | None = self._orchestrator.process_utterance(
            utterance=utterance,
            candidates=harness_candidates,
        )

        if receipt is None:
            return LiveCorrectionExecuteResponse(
                success=False,
                ack_message="未检测到明确的记忆纠偏指令。",
                intent="none",
                mutation=None,
                processing_ms=0.0,
            )

        mutation_dto: MutationResultDTO | None = None
        if receipt.mutated_record is not None:
            mutation_dto = MutationResultDTO(
                action=str(receipt.mutated_record.action.value),
                target_memory_id=receipt.mutated_record.target_memory_id,
                new_memory_id=receipt.mutated_record.new_memory_id,
                status=receipt.mutated_record.status,
                superseded_content=receipt.mutated_record.superseded_content,
                new_content=receipt.mutated_record.new_content,
            )

        return LiveCorrectionExecuteResponse(
            success=receipt.success,
            ack_message=receipt.ack_message,
            intent=str(receipt.intent.value),
            mutation=mutation_dto,
            processing_ms=receipt.processing_ms,
        )


# Global singleton instance
memory_feedback_service = MemoryFeedbackService()
