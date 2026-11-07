"""[INPUT]
- .base::MemorySearchBase (POS: 共享状态)

[OUTPUT]
- MemoryRankingMixin: RRF/排序与 raw exchange 移除

[POS]
`memory/_internal/search_service/` 的排序阶段；只操作已收集的结果。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.retriever import MemoryRetriever
from myrm_agent_harness.toolkits.memory.types import (
    ConversationMemory,
    MemorySearchResult,
)

if TYPE_CHECKING:
    pass

from .base import MemorySearchBase

logger = logging.getLogger(__name__)



class MemoryRankingMixin(MemorySearchBase):
    """RRF/排序与 raw exchange 移除。"""

    def _rank_results(
        self,
        *,
        result_lists: list[list[MemorySearchResult]],
        query: str,
        limit: int,
        use_rrf: bool,
        config: MemoryConfig,
        query_context: object | None = None,
        source_names: list[str] | None = None,
    ) -> list[MemorySearchResult]:
        retriever = MemoryRetriever(config.retrieval) if config != self._config else self._retriever
        if use_rrf and len(result_lists) > 1:
            return retriever.fuse(
                result_lists,
                limit=limit,
                query=query,
                query_context=query_context,
                source_names=source_names,
            )
        merged = [memory for result_list in result_lists for memory in result_list]
        return retriever.rank(merged, limit=limit, query=query, query_context=query_context)


    def _strip_raw_exchange(self, results: list[MemorySearchResult]) -> list[MemorySearchResult]:
        return [
            (
                MemorySearchResult(
                    memory=result.memory.without_raw(), score=result.score, memory_type=result.memory_type
                )
                if isinstance(result.memory, ConversationMemory)
                else result
            )
            for result in results
        ]
