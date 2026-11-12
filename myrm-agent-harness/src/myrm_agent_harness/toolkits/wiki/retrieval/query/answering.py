"""[INPUT]
- .base::WikiQueryBase (POS: 共享状态)
- wiki.core.types::SourceSnippet / WikiIndexTraceHit / WikiRetrievalSeedTrace / WikiRetrievalTrace (POS: 检索追踪与来源片段类型)
- wiki.pipeline.cognitive_map.index_routing::IndexRouteEntry (POS: index-first 路由)

[OUTPUT]
- WikiAnsweringMixin: 拒答判定、答案组装、置信度与检索追踪

[POS]
`wiki/retrieval/query/` 的答案阶段；只读检索结果，不再访问索引。
"""

from __future__ import annotations

from pathlib import Path

from ...core.types import (
    SourceSnippet,
    WikiIndexTraceHit,
    WikiRetrievalSeedTrace,
    WikiRetrievalTrace,
)
from ...pipeline.cognitive_map.index_routing import IndexRouteEntry
from ..best_first import RetrievalSeed
from .base import WikiQueryBase


class WikiAnsweringMixin(WikiQueryBase):
    """拒答判定、答案组装、置信度与检索追踪。"""

    @staticmethod
    def _refused_verdict(confidence: float, min_answer_confidence: float) -> bool:
        """Refusal verdict; out-of-bounds threshold fails closed to refused."""
        if not 0.0 <= min_answer_confidence <= 1.0:
            return True
        return confidence < min_answer_confidence

    @staticmethod
    def _format_vault_prefix(hot_context: str, log_context: str) -> str:
        sections: list[str] = []
        if hot_context:
            sections.append(f"## Recent vault context\n{hot_context}")
        if log_context:
            sections.append(f"## Recent activity log\n{log_context}")
        return "\n\n".join(sections)

    @staticmethod
    def _compose_hot_only_answer(hot_context: str, log_context: str) -> str:
        """Return vault status when no articles match — do not pretend to answer the question."""
        prefix = WikiAnsweringMixin._format_vault_prefix(hot_context, log_context)
        base = "No matching wiki articles were found for this question."
        if prefix:
            return f"{base}\n\n{prefix}"
        return base

    @staticmethod
    def _compose_answer(hot_context: str, log_context: str, article_context: str, question: str) -> str:
        """Prefix wiki_query responses with hot.md and recent log.md when available (zero LLM)."""
        prefix = WikiAnsweringMixin._format_vault_prefix(hot_context, log_context)
        if prefix and article_context:
            return f"{prefix}\n\n## Retrieved articles for: {question}\n{article_context}"
        if prefix:
            return prefix
        return article_context

    @staticmethod
    def _derive_query_confidence(
        *,
        index_matches: list[tuple[IndexRouteEntry, float]],
        seeds: list[RetrievalSeed],
        snippets: list[SourceSnippet],
        article_count: int,
    ) -> float:
        if article_count <= 0:
            return 0.0

        score = 0.45
        if index_matches:
            top_index_score = max(match_score for _entry, match_score in index_matches)
            score += min(0.25, top_index_score * 0.15)

        seed_sources = {seed.source for seed in seeds}
        if "index" in seed_sources:
            score += 0.1
        if "fts" in seed_sources:
            score += 0.08
        if "sidecar" in seed_sources:
            score += 0.05

        claim_snippets = [snippet for snippet in snippets if snippet.claim_id]
        if claim_snippets:
            quality_factors = [WikiAnsweringMixin._claim_snippet_quality_factor(snippet) for snippet in claim_snippets]
            score *= sum(quality_factors) / len(quality_factors)

        return round(min(1.0, max(0.05, score)), 3)

    @staticmethod
    def _claim_snippet_quality_factor(snippet: SourceSnippet) -> float:
        factor = 1.0
        snapshot_status = snippet.evidence_snapshot_status.strip()
        if snapshot_status == "stale":
            factor *= 0.6
        elif snapshot_status == "missing" and snippet.evidence_path.strip():
            factor *= 0.75

        claim_status = snippet.claim_status.strip().lower()
        if claim_status == "contested":
            factor *= 0.7
        elif claim_status == "unsupported":
            factor *= 0.5

        if snippet.claim_confidence > 0.0 and snippet.claim_confidence != 0.5:
            factor *= 1.0 + 0.1 * min(1.0, snippet.claim_confidence)
        return factor

    def _build_retrieval_trace(
        self,
        *,
        index_matches: list[tuple[IndexRouteEntry, float]],
        seeds: list[RetrievalSeed],
        sidecar_directories: list[str],
        article_paths: list[Path],
    ) -> WikiRetrievalTrace | None:
        if not index_matches and not seeds and not sidecar_directories and not article_paths:
            return None

        index_hits = tuple(
            WikiIndexTraceHit(
                link_name=entry.link_name,
                summary=entry.summary,
                score=match_score,
                page_type=entry.page_type,
            )
            for entry, match_score in index_matches[:8]
        )
        seed_traces = tuple(
            WikiRetrievalSeedTrace(
                concept_name=seed.concept_name,
                score=seed.score,
                source=seed.source,
            )
            for seed in seeds[:16]
        )
        selected_concepts = tuple(self._concept_name_from_path(path) for path in article_paths[:16])
        return WikiRetrievalTrace(
            index_hits=index_hits,
            seeds=seed_traces,
            sidecar_directories=tuple(sidecar_directories[:8]),
            selected_concepts=selected_concepts,
        )
