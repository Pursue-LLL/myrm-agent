"""Baseline Search Engine for Comparison

Provides a random-ranking baseline that bounds retrieval quality from below: any working
search engine must rank relevant skills far above chance for the evaluator's metrics to
mean anything.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.meta_tools.skills.search.types import SkillSearchResult

if TYPE_CHECKING:
    from myrm_agent_harness.backends.skills.types import SkillMetadata


class RandomSearchEngine:
    """Random baseline: randomly shuffle skills

    This provides a lower bound for search quality.
    Any reasonable search engine should significantly outperform random ranking.
    """

    def __init__(self, skills: list[SkillMetadata], seed: int = 42) -> None:
        """Initialize random search engine

        Args:
            skills: List of skills to search
            seed: Random seed for reproducibility
        """
        self._skills = list(skills)
        self._random = random.Random(seed)

    def search(self, query: str, top_k: int = 5) -> list[SkillSearchResult]:
        """Random search: shuffle and return top-K

        Args:
            query: Search query (ignored)
            top_k: Number of results to return

        Returns:
            Randomly shuffled top-K skills
        """
        shuffled = self._skills.copy()
        self._random.shuffle(shuffled)

        return [
            SkillSearchResult(name=skill.name, description=skill.description, score=1.0) for skill in shuffled[:top_k]
        ]
