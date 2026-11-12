"""[INPUT]
- .base::WikiQueryBase (POS: 类型与共享状态)
- wiki.pipeline.cognitive_map.index_routing (POS: index-first 路由)
- wiki.retrieval.best_first (POS: best-first 图收敛)
- wiki.retrieval.keyword_fallback::keyword_search (POS: 关键词兜底)

[OUTPUT]
- WikiRetrievalMixin: 概念搜索、检索种子与索引命中

[POS]
`wiki/retrieval/query/` 的检索阶段；只负责找候选，不加载正文或生成答案。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from myrm_agent_harness.utils.logger_utils import get_agent_logger

from ...core.config import WikiQueryConfig
from ...pipeline.cognitive_map.index_routing import (
    IndexRouteEntry,
    match_index_entries,
    read_index_entries,
)
from ..best_first import RetrievalSeed, converge_retrieval_candidates
from ..keyword_fallback import keyword_search
from .base import WikiQueryBase

logger = get_agent_logger(__name__)


@dataclass(frozen=True, slots=True)
class _ConceptSearchResult:
    article_paths: list[Path]
    index_matches: list[tuple[IndexRouteEntry, float]]
    seeds: list[RetrievalSeed]
    sidecar_directories: list[str]


class WikiRetrievalMixin(WikiQueryBase):
    """概念搜索、检索种子与索引命中。"""

    async def _search_concepts(
        self,
        query: str,
        query_config: WikiQueryConfig | None = None,
    ) -> _ConceptSearchResult:
        """Search for relevant concept articles via unified best-first convergence."""
        qc = query_config or self._query_config
        concepts = self._structure.list_concepts()
        if not concepts:
            return _ConceptSearchResult([], [], [], [])

        top_n = qc.max_context_articles
        index_matches = self._resolve_index_matches(query, qc)
        seed_names = [entry.link_name for entry, _score in index_matches]
        if index_matches:
            logger.info("wiki_index_route_hit=true seed_count=%d", len(seed_names))

        scoped_concepts = self._scope_concepts_for_index_seeds(concepts, seed_names)
        valid_names = frozenset(self._concept_name_from_path(path) for path in scoped_concepts) if seed_names else None
        seeds = await self._collect_retrieval_seeds(
            query,
            scoped_concepts,
            index_matches=index_matches,
            seed_names=seed_names,
            top_n=top_n,
            query_config=qc,
        )
        if not seeds:
            keyword_paths = keyword_search(query, scoped_concepts, top_n)
            sidecar_directories = self._sidecar_directories_from_articles(keyword_paths)
            return _ConceptSearchResult(keyword_paths, index_matches, [], sidecar_directories)

        expanded = converge_retrieval_candidates(
            query=query,
            query_config=qc,
            structure=self._structure,
            indexer=self._indexer,
            seeds=seeds,
            max_results=top_n,
            valid_names=valid_names,
        )
        if not expanded and qc.query_mode == "raw_claim":
            expanded = converge_retrieval_candidates(
                query=query,
                query_config=replace(qc, query_mode="auto"),
                structure=self._structure,
                indexer=self._indexer,
                seeds=seeds,
                max_results=top_n,
                valid_names=valid_names,
            )

        resolved: list[Path] = []
        seen_paths: set[Path] = set()
        for name in expanded:
            path = self._structure.resolve_concept_file_path(name)
            if path and path not in seen_paths:
                seen_paths.add(path)
                resolved.append(path)
        sidecar_directories = self._sidecar_directories_from_articles(resolved)
        return _ConceptSearchResult(resolved[:top_n], index_matches, seeds, sidecar_directories)

    async def _collect_retrieval_seeds(
        self,
        query: str,
        scoped_concepts: list[Path],
        *,
        index_matches: list[tuple[IndexRouteEntry, float]],
        seed_names: list[str],
        top_n: int,
        query_config: WikiQueryConfig,
    ) -> list[RetrievalSeed]:
        seeds: list[RetrievalSeed] = []
        seen: set[str] = set()

        def add_seed(name: str, score: float, source: str) -> None:
            normalized = self._normalize_concept_name(name)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            seeds.append(RetrievalSeed(normalized, score, source))

        for entry, score in index_matches:
            add_seed(entry.link_name, score, "index")

        if query_config.sidecar_retrieval_enabled:
            sidecar_names = await self._collect_sidecar_seed_names(
                query,
                scoped_concepts,
                top_n=top_n,
                seed_names=seed_names,
                query_config=query_config,
            )
            for index, name in enumerate(sidecar_names):
                add_seed(name, max(0.4, 1.0 - index * 0.05), "sidecar")

        if self._config.enable_semantic_search:
            if self._search_fn is not None:
                try:
                    results = await self._search_fn(query, top_n)
                    for path, score in results[:top_n]:
                        add_seed(self._concept_name_from_path(path), float(score), "fts")
                except Exception as e:
                    logger.warning(f"Injected search_fn failed: {e}")

            try:
                results = await self._indexer.search(query, limit=max(top_n * 6, 20))
                for concept_name, score in results:
                    add_seed(concept_name, float(score), "fts")
                    if len(seeds) >= top_n * 3:
                        break
            except Exception as e:
                logger.warning(f"FTS5 semantic search failed: {e}")

        if len(seeds) < top_n:
            for path in keyword_search(query, scoped_concepts, top_n):
                add_seed(self._concept_name_from_path(path), 0.35, "keyword")

        return seeds

    def _resolve_index_matches(
        self,
        query: str,
        query_config: WikiQueryConfig | None = None,
    ) -> list[tuple[IndexRouteEntry, float]]:
        qc = query_config or self._query_config
        if not qc.index_first_enabled:
            return []
        entries = read_index_entries(self._structure)
        if not entries:
            return []
        return match_index_entries(
            query,
            entries,
            max_hits=max(1, qc.max_index_hits),
            min_score=qc.index_min_match_score,
        )

    def _scope_concepts_for_index_seeds(self, concepts: list[Path], seed_names: list[str]) -> list[Path]:
        if not seed_names:
            return concepts
        seed_dirs = self._directories_from_seed_names(seed_names)
        if not seed_dirs:
            return concepts
        scoped = self._collect_concepts_from_directory_scopes(seed_dirs, concepts)
        return scoped if scoped else concepts

    @staticmethod
    def _directories_from_seed_names(seed_names: list[str]) -> list[str]:
        ordered_dirs: list[str] = []
        seen_dirs: set[str] = set()
        for seed_name in seed_names:
            parent = Path(seed_name).parent
            if str(parent) in (".", ""):
                continue
            normalized = str(parent).replace("\\", "/").strip("/")
            if normalized and normalized not in seen_dirs:
                seen_dirs.add(normalized)
                ordered_dirs.append(normalized)
        return ordered_dirs

    async def _collect_sidecar_seed_names(
        self,
        query: str,
        concepts: list[Path],
        *,
        top_n: int,
        seed_names: list[str] | None = None,
        query_config: WikiQueryConfig | None = None,
    ) -> list[str]:
        """Use L0/L1 sidecars to collect concept seed names for best-first convergence."""
        qc = query_config or self._query_config
        limit = max(top_n * 3, 8)
        try:
            sidecar_hits = await self._indexer.search_sidecars(query, limit=limit)
        except Exception as e:
            logger.warning("Sidecar retrieval failed: %s", e)
            return []
        if not sidecar_hits:
            return []

        max_dirs = max(0, qc.max_sidecar_directories)
        if max_dirs == 0:
            return []
        ordered_dirs: list[str] = []
        seen_dirs: set[str] = set()
        for dir_path, _level, _score in sidecar_hits:
            if dir_path in seen_dirs:
                continue
            seen_dirs.add(dir_path)
            ordered_dirs.append(dir_path)
            if len(ordered_dirs) >= max_dirs:
                break
        if not ordered_dirs:
            return []

        candidates = self._collect_concepts_from_directory_scopes(ordered_dirs, concepts)
        if not candidates:
            return []

        candidate_name_to_path = {self._concept_name_from_path(path): path for path in candidates}
        ranked_names: list[str] = []
        if seed_names:
            for concept_name in seed_names:
                if concept_name in candidate_name_to_path and concept_name not in ranked_names:
                    ranked_names.append(concept_name)
                if len(ranked_names) >= top_n:
                    break
        try:
            indexed_hits = await self._indexer.search(query, limit=max(top_n * 6, 20))
            for concept_name, _score in indexed_hits:
                if concept_name in candidate_name_to_path and concept_name not in ranked_names:
                    ranked_names.append(concept_name)
                if len(ranked_names) >= top_n:
                    break
        except Exception as e:
            logger.warning("Concept rerank after sidecar routing failed: %s", e)

        if len(ranked_names) < top_n:
            for path in keyword_search(query, candidates, top_n):
                concept_name = self._concept_name_from_path(path)
                if concept_name not in ranked_names:
                    ranked_names.append(concept_name)
                if len(ranked_names) >= top_n:
                    break

        if ranked_names:
            return [name for name in ranked_names if name in candidate_name_to_path]
        return [self._concept_name_from_path(path) for path in candidates[:top_n]]

    def _sidecar_directories_from_articles(self, article_paths: list[Path]) -> list[str]:
        ordered_dirs: list[str] = []
        seen_dirs: set[str] = set()
        for article in article_paths:
            try:
                rel = article.relative_to(self._structure.concepts_dir).with_suffix("")
            except ValueError:
                continue
            dir_path = "" if str(rel.parent) in (".", "") else str(rel.parent).replace("\\", "/")
            if not dir_path or dir_path in seen_dirs:
                continue
            seen_dirs.add(dir_path)
            ordered_dirs.append(dir_path)
        return ordered_dirs
