"""[INPUT] AnalyzeFailureRequest, StructuredFailureFactDTO, AnalyzeFailureResponse, SubagentFailureHistoryResponse.
[OUTPUT] FailureFactsService managing privacy-preserving subagent error categorization, single-line diagnostic headers, and bounded history.
[POS] Service layer for Subagent Bounded Structured Failure Facts subsystem.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from myrm_agent_harness.agent.sub_agents.failure_facts import (
    StructuredFailureFact,
    SubagentDiagnosticProtocol,
    SubagentFailureCategory,
    SubagentFailureStage,
)

from app.schemas.failure_facts import (
    AnalyzeFailureRequest,
    StructuredFailureFactDTO,
    SubagentFailureHistoryResponse,
)

logger = logging.getLogger(__name__)


def _to_dto(fact: StructuredFailureFact) -> StructuredFailureFactDTO:
    """Convert harness StructuredFailureFact domain model to schema DTO."""
    return StructuredFailureFactDTO(
        product=fact.product,
        stage=fact.stage.value,
        category=fact.category.value,
        http_status=fact.http_status,
        exit_code=fact.exit_code,
        signal=fact.signal,
        sanitized_message=fact.sanitized_message,
        remediation=fact.remediation.value,
        safe_diagnostic_header=fact.safe_diagnostic_header,
        byte_size=fact.byte_size,
        timestamp=fact.timestamp,
        metadata=dict(fact.metadata),
    )


class FailureFactsService:
    """Session-isolated management for subagent failure facts and safe diagnostics."""

    def __init__(self, max_history_per_chat: int = 50) -> None:
        self.max_history_per_chat = max_history_per_chat
        self._history: Dict[str, List[StructuredFailureFact]] = {}

    def diagnose_failure(
        self,
        chat_id: str,
        req: AnalyzeFailureRequest,
    ) -> StructuredFailureFactDTO:
        """Diagnose subagent failure into a machine-actionable fact, scrub secrets, and record history."""
        stage = SubagentFailureStage(req.stage) if req.stage in SubagentFailureStage._value2member_map_ else SubagentFailureStage.TURN
        category = (
            SubagentFailureCategory(req.category)
            if req.category and req.category in SubagentFailureCategory._value2member_map_
            else None
        )

        fact = SubagentDiagnosticProtocol.create_failure_fact(
            product=req.product,
            stage=stage,
            raw_message=req.raw_message,
            category=category,
            http_status=req.http_status,
            exit_code=req.exit_code,
            signal=req.signal,
            metadata=req.metadata,
        )

        if chat_id not in self._history:
            self._history[chat_id] = []

        history_list = self._history[chat_id]
        history_list.append(fact)
        if len(history_list) > self.max_history_per_chat:
            history_list.pop(0)

        logger.info(
            "Diagnosed failure for session %s: %s (bytes=%d)",
            chat_id,
            fact.safe_diagnostic_header,
            fact.byte_size,
        )
        return _to_dto(fact)

    def get_history(self, chat_id: str) -> SubagentFailureHistoryResponse:
        """Fetch recorded failure facts history for a given chat session."""
        facts = self._history.get(chat_id, [])
        return SubagentFailureHistoryResponse(
            total_count=len(facts),
            facts=[_to_dto(f) for f in facts],
        )

    def cleanup_chat(self, chat_id: str) -> bool:
        """Release failure facts history for a terminated chat session."""
        if chat_id in self._history:
            del self._history[chat_id]
            logger.info("Cleaned up failure facts history for session %s", chat_id)
            return True
        return False


_instance: Optional[FailureFactsService] = None


def get_failure_facts_service() -> FailureFactsService:
    """Singleton getter for FailureFactsService."""
    global _instance
    if _instance is None:
        _instance = FailureFactsService()
    return _instance
