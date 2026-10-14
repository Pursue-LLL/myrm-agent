"""Business service implementing failure-triggered historical session retrieval (Item 109).

[POS]
app/services/memory/failure_search_service.py

[INPUT]
- app.schemas.failure_search, myrm_agent_harness.toolkits.memory

[OUTPUT]
- FailureSearchService, get_failure_search_service
"""


from __future__ import annotations

import logging
from functools import lru_cache

from myrm_agent_harness.toolkits.memory import (
    ErrorFingerprint,
    ErrorFingerprintExtractor,
    FailureHistoricalSessionSearchEngine,
    FailureRetrievalResult,
    FailureTriggerConfig,
    HistoricalResolutionEntry,
)

from app.schemas.failure_search import (
    ErrorFingerprintDTO,
    FailureRetrievalResultDTO,
    FailureTriggerConfigDTO,
    HistoricalResolutionEntryDTO,
    SearchFailureRequest,
)

logger = logging.getLogger(__name__)


def _fingerprint_to_dto(fp: ErrorFingerprint) -> ErrorFingerprintDTO:
    """Map internal domain fingerprint to API DTO."""
    return ErrorFingerprintDTO(
        error_type=fp.error_type,
        tool_name=fp.tool_name,
        normalized_pattern=fp.normalized_pattern,
        exit_code=fp.exit_code,
        context_tags=list(fp.context_tags),
    )


def _entry_to_dto(entry: HistoricalResolutionEntry) -> HistoricalResolutionEntryDTO:
    """Map internal domain historical entry to API DTO."""
    return HistoricalResolutionEntryDTO(
        entry_id=entry.entry_id,
        session_id=entry.session_id,
        turn_index=entry.turn_index,
        error_signature=entry.error_signature,
        outcome_type=entry.outcome_type.value,
        solution_snippet=entry.solution_snippet,
        explanation=entry.explanation,
        confidence=entry.confidence,
        created_at=entry.created_at,
    )


def _result_to_dto(result: FailureRetrievalResult) -> FailureRetrievalResultDTO:
    """Map internal retrieval result to API DTO."""
    return FailureRetrievalResultDTO(
        query_fingerprint=_fingerprint_to_dto(result.query_fingerprint),
        total_matched=result.total_matched,
        successful_resolutions=[_entry_to_dto(e) for e in result.successful_resolutions],
        cautionary_failures=[_entry_to_dto(e) for e in result.cautionary_failures],
        suggested_action=result.suggested_action,
    )


class FailureSearchService:
    """Service encapsulating historical session error retrieval."""

    def __init__(self) -> None:
        self._search_engine = FailureHistoricalSessionSearchEngine()
        self._extractor = ErrorFingerprintExtractor()
        self._config = FailureTriggerConfig()

    def search_resolutions(self, req: SearchFailureRequest) -> FailureRetrievalResultDTO:
        """Search historical sessions using raw error message or trace."""
        fingerprint = self._extractor.extract(
            raw_error=req.error_message,
            tool_name=req.tool_name,
            exit_code=req.exit_code,
        )
        result = self._search_engine.search(
            fingerprint=fingerprint,
            top_n=req.top_n,
            include_cautionary=req.include_cautionary,
        )
        return _result_to_dto(result)

    def list_resolutions(self) -> list[HistoricalResolutionEntryDTO]:
        """List all indexed historical resolution entries."""
        entries = self._search_engine.list_entries()
        return [_entry_to_dto(e) for e in entries]

    def get_config(self) -> FailureTriggerConfigDTO:
        """Get current automated failure retrieval configuration."""
        return FailureTriggerConfigDTO(
            enabled=self._config.enabled,
            auto_trigger_on_error=self._config.auto_trigger_on_error,
            max_matches=self._config.max_matches,
            min_similarity_threshold=self._config.min_similarity_threshold,
            include_cautionary_failures=self._config.include_cautionary_failures,
        )

    def update_config(self, new_cfg: FailureTriggerConfigDTO) -> FailureTriggerConfigDTO:
        """Update failure retrieval configuration."""
        self._config.enabled = new_cfg.enabled
        self._config.auto_trigger_on_error = new_cfg.auto_trigger_on_error
        self._config.max_matches = new_cfg.max_matches
        self._config.min_similarity_threshold = new_cfg.min_similarity_threshold
        self._config.include_cautionary_failures = new_cfg.include_cautionary_failures
        return self.get_config()


@lru_cache(maxsize=1)
def get_failure_search_service() -> FailureSearchService:
    """Dependency provider returning singleton FailureSearchService."""
    return FailureSearchService()
