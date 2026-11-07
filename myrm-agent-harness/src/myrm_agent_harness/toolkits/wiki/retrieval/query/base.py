"""[INPUT]
- langchain_core.language_models::BaseChatModel (POS: LLM 基类)
- wiki.core.config::WikiConfig / WikiQueryConfig (POS: Wiki 配置)
- wiki.core.structure::WikiStructure (POS: Wiki 文件系统抽象)
- wiki.retrieval.indexer::WikiIndexer (POS: FTS5 索引器)
- wiki.retrieval.asset_index::WikiAssetIndexer (POS: 资产索引器)

[OUTPUT]
- SemanticSearchFn: 语义检索函数签名
- WikiQueryBase: 查询引擎的实例状态与跨阶段方法声明

[POS]
`wiki/retrieval/query/` 的类型与共享状态；各阶段 mixin 都继承它。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ...core.config import WikiConfig, WikiQueryConfig
    from ...core.structure import WikiStructure
    from ...pipeline.cognitive_map.index_routing import IndexRouteEntry
    from ..asset_index import WikiAssetIndexer
    from ..best_first import RetrievalSeed
    from ..indexer import WikiIndexer

SemanticSearchFn = Callable[[str, int], Awaitable[list[tuple[Path, float]]]]


class WikiQueryBase:
    """Instance state is created by WikiQueryEngine.__init__."""

    _llm: BaseChatModel
    _structure: WikiStructure
    _config: WikiConfig
    _query_config: WikiQueryConfig
    _search_fn: SemanticSearchFn | None
    _indexer: WikiIndexer
    _asset_indexer: WikiAssetIndexer | None

    # 跨 mixin 调用：实现位于 loading / retrieval / answering。
    def _concept_name_from_path(self, path: Path) -> str:
        raise NotImplementedError
    def _collect_concepts_from_directory_scopes(self, dir_paths: list[str], concepts: list[Path]) -> list[Path]:
        raise NotImplementedError
    def _normalize_concept_name(self, name: str) -> str:
        raise NotImplementedError

    def _build_retrieval_trace(
        self,
        *,
        index_matches: list[tuple[IndexRouteEntry, float]],
        seeds: list[RetrievalSeed],
        sidecar_directories: list[str],
        article_paths: list[Path],
    ) -> object:
        raise NotImplementedError
