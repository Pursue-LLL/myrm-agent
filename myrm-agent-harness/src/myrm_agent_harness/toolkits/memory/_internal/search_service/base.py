"""[INPUT]
- memory 的类型、配置与存储协议（POS: 检索服务依赖的基础类型）

[OUTPUT]
- MemorySearchBase: 检索服务实例状态与跨阶段方法声明
- FTS5SearcherFunc: FTS5 检索函数签名

[POS]
`memory/_internal/search_service/` 的共享状态；各阶段 mixin 都继承它。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.observability import (
    MemoryRetrievalTrace,
)
from myrm_agent_harness.toolkits.memory.types import (
    MemorySearchResult,
    MemoryType,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.protocols.cache import EmbeddingCacheProtocol
    from myrm_agent_harness.toolkits.memory.protocols.embedding import EmbeddingProtocol
    from myrm_agent_harness.toolkits.memory.protocols.graph import GraphStoreProtocol
    from myrm_agent_harness.toolkits.memory.protocols.relational import RelationalStoreProtocol
    from myrm_agent_harness.toolkits.memory.protocols.vector import VectorStoreProtocol
    from myrm_agent_harness.toolkits.memory.retriever import MemoryRetriever
    from myrm_agent_harness.toolkits.retriever.reranker.base import RerankerService

logger = logging.getLogger(__name__)


class MemorySearchBase:
    """Instance state is created by MemorySearchService.__init__."""

    _config: MemoryConfig
    _namespaces: list[str]
    _current_channel_id: str | None
    _last_trace: MemoryRetrievalTrace | None
    _vector: VectorStoreProtocol | None
    _relational: RelationalStoreProtocol | None
    _graph: GraphStoreProtocol | None
    _embedding: EmbeddingProtocol | None
    _cache: EmbeddingCacheProtocol | None
    _reranker: RerankerService | None
    _retriever: MemoryRetriever
    _fts5_searcher: FTS5SearcherFunc | None

    async def _collect_result_lists(
        self,
        *,
        query: str,
        memory_types: list[MemoryType],
        limit: int,
        include_raw: bool,
        config: MemoryConfig,
        query_vector: list[float] | None,
        deadline: float,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[list[list[MemorySearchResult]], bool, list[str], list[str]]:
        raise NotImplementedError

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
        raise NotImplementedError

    def _strip_raw_exchange(self, results: list[MemorySearchResult]) -> list[MemorySearchResult]:
        raise NotImplementedError


class FTS5SearcherFunc(Protocol):
    """Exact-identifier search; ``namespaces`` limits hits to the namespaces the caller may read."""

    def __call__(
        self,
        query: str,
        limit: int,
        since: datetime | None,
        until: datetime | None,
        *,
        namespaces: list[str] | None = None,
    ) -> Awaitable[list[MemorySearchResult]]: ...
