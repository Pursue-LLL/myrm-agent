# [POS]: app/services/memory/failure_search_service.py
# [INPUT]: app.schemas.failure_search, myrm_agent_harness.toolkits.memory
# [OUTPUT]: FailureSearchService, get_failure_search_service

"""Business service implementing failure-triggered historical session retrieval (Item 109)."""

from __future__ import annotations

import logging
from functools import lru_cache

from myrm_agent_harness.toolkits.memory import (
    ErrorFingerprint,
    ErrorFingerprintExtractor,
    FailureHistoricalSessionSearchEngine,
    FailureOutcomeType,
    FailureRetrievalResult,
    FailureTriggerConfig,
    FailureTriggerInterceptor,
    HistoricalResolutionEntry,
)

from app.schemas.failure_search import (
    ErrorFingerprintDTO,
    FailureRetrievalResultDTO,
    FailureTriggerConfigDTO,
    HistoricalResolutionEntryDTO,
    InterceptFailureRequest,
    InterceptFailureResponseDTO,
    RecordHistoricalResolutionRequest,
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
    """Service encapsulating historical session error retrieval and interceptor."""

    def __init__(self) -> None:
        self._search_engine = FailureHistoricalSessionSearchEngine()
        self._extractor = ErrorFingerprintExtractor()
        self._config = FailureTriggerConfig()
        self._interceptor = FailureTriggerInterceptor(
            search_engine=self._search_engine,
            extractor=self._extractor,
            config=self._config,
        )

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

    def index_resolution(self, req: RecordHistoricalResolutionRequest) -> HistoricalResolutionEntryDTO:
        """Index a new historical resolution or cautionary attempt."""
        outcome = (
            FailureOutcomeType.CAUTIONARY_FAILURE
            if req.outcome_type == FailureOutcomeType.CAUTIONARY_FAILURE.value
            else FailureOutcomeType.SUCCESSFUL_RESOLUTION
        )
        entry = HistoricalResolutionEntry(
            entry_id=req.entry_id,
            session_id=req.session_id,
            turn_index=req.turn_index,
            error_signature=req.error_signature,
            outcome_type=outcome,
            solution_snippet=req.solution_snippet,
            explanation=req.explanation,
            confidence=req.confidence,
        )
        self._search_engine.index_resolution(entry)
        return _entry_to_dto(entry)

    def get_resolution(self, session_id: str, turn_index: int | None = None) -> HistoricalResolutionEntryDTO | None:
        """Directly retrieve resolution from session without guessing."""
        entry = self._search_engine.read_session_resolution(session_id=session_id, turn_index=turn_index)
        if entry is None:
            return None
        return _entry_to_dto(entry)

    def list_resolutions(self) -> list[HistoricalResolutionEntryDTO]:
        """List all indexed historical resolution entries."""
        entries = self._search_engine.list_entries()
        return [_entry_to_dto(e) for e in entries]

    def intercept_failure(self, req: InterceptFailureRequest) -> InterceptFailureResponseDTO:
        """Intercept tool failure and produce formatted markdown injection block."""
        retrieval_res = self._interceptor.on_execution_failure(
            raw_error=req.error_content,
            tool_name=req.tool_name,
            exit_code=req.exit_code,
        )
        if retrieval_res and retrieval_res.total_matched > 0:
            prompt_block = self._interceptor.format_resolution_guidance(retrieval_res)
            return InterceptFailureResponseDTO(
                should_inject=True,
                injected_prompt_block=prompt_block,
                result=_result_to_dto(retrieval_res),
            )
        return InterceptFailureResponseDTO(
            should_inject=False,
            injected_prompt_block="",
            result=None,
        )

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
