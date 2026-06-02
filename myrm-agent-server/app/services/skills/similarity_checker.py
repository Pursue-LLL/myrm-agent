"""Skill similarity checker implementation using HybridSkillSearchEngine.

[INPUT]
- myrm_agent_harness.backends.skills.similarity::SkillSimilarityChecker, SimilarSkillInfo
  (POS: Skill similarity checking protocol)
- myrm_agent_harness.agent.meta_tools.skills.search.hybrid_engine::HybridSkillSearchEngine
  (POS: Hybrid search engine combining BM25 + Embedding)

[OUTPUT]
- HybridSimilarityChecker: SkillSimilarityChecker implementation backed by HybridSkillSearchEngine.

[POS]
Business-layer skill similarity checker. Uses the framework's HybridSkillSearchEngine
to find semantically similar skills when a new skill is being created, preventing
skill entropy (accumulation of functionally duplicate skills).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.backends.skills.similarity import SimilarSkillInfo, SkillSimilarityChecker

if TYPE_CHECKING:
    from myrm_agent_harness.agent.meta_tools.skills.search.hybrid_engine import HybridSkillSearchEngine

logger = logging.getLogger(__name__)


class HybridSimilarityChecker(SkillSimilarityChecker):
    """SkillSimilarityChecker backed by HybridSkillSearchEngine.

    Delegates to the hybrid engine's BM25+Embedding search to find skills
    that are semantically similar to a proposed new skill.
    """

    def __init__(self, engine: HybridSkillSearchEngine) -> None:
        self._engine = engine

    async def find_similar(
        self,
        name: str,
        description: str,
        *,
        top_k: int = 3,
        threshold: float = 0.6,
    ) -> list[SimilarSkillInfo]:
        query = f"{name} {description}".strip()
        if not query:
            return []

        results = await self._engine.search_bm25(query, top_k=top_k + 2)

        similar: list[SimilarSkillInfo] = []
        for r in results:
            if r.name == name:
                continue
            if r.score >= threshold:
                similar.append(SimilarSkillInfo(name=r.name, description=r.description, similarity_score=r.score))
            if len(similar) >= top_k:
                break

        return similar
