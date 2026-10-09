"""Provider for CJK iteration mark disambiguation and recall matching service.

[POS]
Adapter layer between FastAPI controllers and the core harness CJK iteration mark engine.
Converts domain entities into Pydantic V2 DTOs with strictly typed, zero-Any contracts.

[INPUT]
- app.schemas.cjk_iteration
- myrm_agent_harness.toolkits.memory.cjk_iteration_mark.facade

[OUTPUT]
- CjkIterationServiceProvider
- get_cjk_iteration_service_provider
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.cjk_iteration_mark.facade import (
    CjkIterationMarkFacade,
    get_cjk_iteration_mark_facade,
)
from myrm_agent_harness.toolkits.memory.cjk_iteration_mark.models import (
    CjkRecallMatchScore,
    DisambiguatedCjkTokens,
    IterationExpansionResult,
    IterationMarkRun,
)

from app.schemas.cjk_iteration import (
    DisambiguateCjkRequest,
    DisambiguateCjkResponse,
    DisambiguatedCjkTokensDTO,
    IterationMarkRunDTO,
    MatchCjkRecallRequest,
    MatchCjkRecallResponse,
)


class CjkIterationServiceProvider:
    """Service adapter exposing CJK iteration mark expansion and recall scoring."""

    def __init__(self, facade: CjkIterationMarkFacade | None = None) -> None:
        self._facade: CjkIterationMarkFacade = facade or get_cjk_iteration_mark_facade()

    def disambiguate(self, request: DisambiguateCjkRequest) -> DisambiguateCjkResponse:
        """Resolves ideographic iteration marks and constructs token matrices."""
        result: IterationExpansionResult = self._facade.disambiguate(request.text)
        return self._map_to_disambiguate_response(result)

    def match(self, request: MatchCjkRecallRequest) -> MatchCjkRecallResponse:
        """Calculates bidirectional recall match score taking iteration marks into account."""
        score: CjkRecallMatchScore = self._facade.match(
            query=request.query,
            target_text=request.target_text,
            threshold=request.threshold,
        )
        return self._map_to_match_response(score)

    @staticmethod
    def _map_to_tokens_dto(tokens: DisambiguatedCjkTokens) -> DisambiguatedCjkTokensDTO:
        return DisambiguatedCjkTokensDTO(
            raw_tokens=list(tokens.raw_tokens),
            normalized_tokens=list(tokens.normalized_tokens),
            anchor_tokens=list(tokens.anchor_tokens),
            all_tokens=sorted(tokens.all_tokens),
        )

    @staticmethod
    def _map_to_run_dto(run: IterationMarkRun) -> IterationMarkRunDTO:
        return IterationMarkRunDTO(
            raw_run=run.raw_run,
            expanded_run=run.expanded_run,
            expanded_indices=list(run.expanded_indices),
            raw_bigrams=list(run.raw_bigrams),
            normalized_bigrams=list(run.normalized_bigrams),
            anchor_bigrams=list(run.anchor_bigrams),
        )

    def _map_to_disambiguate_response(
        self,
        result: IterationExpansionResult,
    ) -> DisambiguateCjkResponse:
        return DisambiguateCjkResponse(
            original_text=result.original_text,
            normalized_text=result.normalized_text,
            has_iteration_mark=result.has_iteration_mark,
            marks_expanded_count=result.marks_expanded_count,
            runs=[self._map_to_run_dto(run) for run in result.runs],
            tokens=self._map_to_tokens_dto(result.tokens),
        )

    @staticmethod
    def _map_to_match_response(score: CjkRecallMatchScore) -> MatchCjkRecallResponse:
        return MatchCjkRecallResponse(
            query=score.query,
            target=score.target,
            is_matched=score.is_matched,
            raw_overlap_count=score.raw_overlap_count,
            normalized_overlap_count=score.normalized_overlap_count,
            anchor_overlap_count=score.anchor_overlap_count,
            composite_score=score.composite_score,
            matched_tokens=list(score.matched_tokens),
        )


_PROVIDER_INSTANCE: CjkIterationServiceProvider | None = None


def get_cjk_iteration_service_provider() -> CjkIterationServiceProvider:
    """Returns singleton instance of CjkIterationServiceProvider."""
    global _PROVIDER_INSTANCE
    if _PROVIDER_INSTANCE is None:
        _PROVIDER_INSTANCE = CjkIterationServiceProvider()
    return _PROVIDER_INSTANCE
