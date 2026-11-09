"""[INPUT]
- .base::MemorySearchBase (POS: 共享状态)
- .helpers::_log_background_task_failure / _stream_warning_code (POS: 纯函数助手)

[OUTPUT]
- MemoryCollectionMixin: 按类型扇出检索、并发收集、失败降级与结果过滤

[POS]
`memory/_internal/search_service/` 的收集阶段；只负责拿到各流结果。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from myrm_agent_harness.toolkits.memory._assistant_retrieval import search_conversation_two_pass
from myrm_agent_harness.toolkits.memory._internal.bm25_sparse import bm25_scope
from myrm_agent_harness.toolkits.memory._internal.deadline_budget import deadline_remaining
from myrm_agent_harness.toolkits.memory._internal.scope import apply_channel_affinity
from myrm_agent_harness.toolkits.memory._internal.storage import (
    search_bm25,
    search_conversation,
    search_episodic,
    search_procedural,
    search_profile,
    search_semantic,
)
from myrm_agent_harness.toolkits.memory._internal.storage_converters import doc_to_semantic
from myrm_agent_harness.toolkits.memory.adaptive import should_use_dual_channel
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.metrics import get_search_metrics
from myrm_agent_harness.toolkits.memory.protocols.vector import VectorStoreProtocol
from myrm_agent_harness.toolkits.memory.query_analyzer import is_assistant_reference_query
from myrm_agent_harness.toolkits.memory.types import (
    MemorySearchResult,
    MemoryType,
    ProceduralMemory,
)

if TYPE_CHECKING:
    pass

from .base import FTS5SearcherFunc, MemorySearchBase
from .helpers import _stream_warning_code

logger = logging.getLogger(__name__)


_SUPERSEDED_KEY = "superseded"


class MemoryCollectionMixin(MemorySearchBase):
    """按类型扇出检索、并发收集、失败降级与结果过滤。"""

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
        """Fan out per-type store searches and collect results under one deadline.

        Returns ``(result_lists, degraded, warning_codes, source_names)``. Store tasks that outlive the
        shared wall-clock deadline are cancelled and completed results kept, so a hanging store degrades
        recall; a stop aimed at this task cancels the store tasks it awaits, then lets the stop continue.
        """
        tasks: list[asyncio.Task[list[MemorySearchResult]]] = []
        task_stream_map: dict[asyncio.Task[Any], str] = {}
        for memory_type in memory_types:
            self._append_type_search_tasks(
                tasks,
                task_stream_map,
                memory_type=memory_type,
                query=query,
                limit=limit,
                include_raw=include_raw,
                config=config,
                query_vector=query_vector,
                since=since,
                until=until,
            )

        bm25_types = bm25_scope(memory_types)
        if self._vector is not None and bm25_types:
            bm25_task = asyncio.create_task(
                search_bm25(
                    query,
                    self._vector,
                    config,
                    memory_types=bm25_types,
                    namespaces=self._namespaces,
                    since=since,
                    until=until,
                )
            )
            tasks.append(bm25_task)
            task_stream_map[bm25_task] = "bm25"

        if self._fts5_searcher is not None:
            fts_t = asyncio.create_task(self._search_exact_stream(self._fts5_searcher, query, limit, since, until))
            tasks.append(fts_t)
            task_stream_map[fts_t] = "fts5"

        if not tasks:
            return [], False, [], []

        try:
            done, pending = await asyncio.wait(
                tasks,
                timeout=deadline_remaining(deadline),
                return_when=asyncio.ALL_COMPLETED,
            )
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        degraded = False
        warning_codes: list[str] = []
        if pending:
            degraded = True
            timeout_seconds = self._config.retrieval.timeout_seconds
            for task in pending:
                task.cancel()
                stream = task_stream_map.get(task, "unknown")
                warning_codes.append(_stream_warning_code(stream, "timeout"))
            await asyncio.gather(*pending, return_exceptions=True)
            get_search_metrics().record_degradation("timeout")
            logger.warning(
                "Memory search collect timed out after %.1fs; returning %d/%d completed store results",
                timeout_seconds,
                len(done),
                len(tasks),
            )

        result_lists: list[list[MemorySearchResult]] = []
        source_names: list[str] = []
        for task in done:
            stream = task_stream_map.get(task, "unknown")
            try:
                result = task.result()
            except BaseException as exc:
                degraded = True
                warning_codes.append(_stream_warning_code(stream, "failed"))
                get_search_metrics().record_degradation("error")
                logger.warning("Memory search error (%s): %s", stream, exc)
                continue
            if isinstance(result, list) and result:
                filtered = self._filter_results(result)
                if filtered:
                    result_lists.append(apply_channel_affinity(filtered, current_channel_id=self._current_channel_id))
                    source_names.append(stream)
        return result_lists, degraded, warning_codes, source_names

    async def _search_exact_stream(
        self,
        searcher: FTS5SearcherFunc,
        query: str,
        limit: int,
        since: datetime | None,
        until: datetime | None,
    ) -> list[MemorySearchResult]:
        """Exact-identifier stream limited to this manager's namespaces.

        The side index only locates candidates. Each hit is replaced by the stored memory so status,
        scope and timestamps come from the vector store, and an index row whose memory is gone is dropped.
        """
        hits = await searcher(query, limit, since, until, namespaces=self._namespaces)
        if not hits or self._vector is None:
            return hits
        docs = await self._vector.get(self._config.semantic_collection, [hit.memory.id for hit in hits])
        stored = {doc.id: doc for doc in docs}
        return [
            hit.model_copy(update={"memory": doc_to_semantic(stored[hit.memory.id])})
            for hit in hits
            if hit.memory.id in stored
        ]

    @staticmethod
    def _filter_results(results: list[MemorySearchResult]) -> list[MemorySearchResult]:
        """Hide internal L2 task digests, archive checkpoints, and subsumed memories from normal recall results.

        Task digests are compilation artifacts for the L2 -> L3 pipeline.
        Archive checkpoints are internal prune milestones for pre-compaction inject.
        Subsumed memories are redundant memories that have been incorporated into skills/wiki.
        """
        filtered: list[MemorySearchResult] = []
        for result in results:
            mem = result.memory
            status = getattr(mem, "status", None)
            status_str = str(getattr(status, "value", status or "")).strip().lower()
            if status_str in ("archived", "disabled"):
                continue
            meta = getattr(mem, "metadata", None)
            if isinstance(meta, dict):
                meta_status = str(meta.get("status", "")).strip().lower()
                if meta.get("archived") is True or meta_status in ("archived", "disabled"):
                    continue
                # A choice the user explicitly withdrew. Every search stream passes
                # through here, so one place stops the agent repeating it.
                if meta.get(_SUPERSEDED_KEY) is True:
                    continue
            if isinstance(mem, ProceduralMemory) and not mem.is_active:
                continue

            if result.memory_type != MemoryType.EPISODIC:
                filtered.append(result)
                continue

            event_type = str(getattr(result.memory, "event_type", "")).strip()
            if event_type in {MemoryType.TASK_DIGEST.value, "archive_checkpoint"}:
                continue
            filtered.append(result)
        return filtered

    def _append_type_search_tasks(
        self,
        tasks: list[asyncio.Task[list[MemorySearchResult]]],
        task_stream_map: dict[asyncio.Task[Any], str],
        *,
        memory_type: MemoryType,
        query: str,
        limit: int,
        include_raw: bool,
        config: MemoryConfig,
        query_vector: list[float] | None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> None:
        if memory_type == MemoryType.PROFILE and self._relational is not None:
            t = asyncio.create_task(search_profile(query, limit, self._relational, namespaces=self._namespaces))
            tasks.append(t)
            task_stream_map[t] = "profile"
            return
        if memory_type == MemoryType.PROCEDURAL and self._relational is not None:
            t = asyncio.create_task(search_procedural(query, limit, self._relational, namespaces=self._namespaces))
            tasks.append(t)
            task_stream_map[t] = "procedural"
            return
        if memory_type == MemoryType.SEMANTIC and self._vector is not None and query_vector is not None:
            t = asyncio.create_task(
                search_semantic(
                    query_vector,
                    limit,
                    self._vector,
                    config,
                    namespaces=self._namespaces,
                    since=since,
                    until=until,
                )
            )
            tasks.append(t)
            task_stream_map[t] = "semantic"
            return
        if memory_type == MemoryType.EPISODIC and self._vector is not None and query_vector is not None:
            t = asyncio.create_task(
                search_episodic(
                    query_vector,
                    limit,
                    self._vector,
                    config,
                    namespaces=self._namespaces,
                    since=since,
                    until=until,
                )
            )
            tasks.append(t)
            task_stream_map[t] = "episodic"
            return
        if memory_type == MemoryType.CONVERSATION and self._vector is not None and query_vector is not None:
            self._append_conversation_tasks(
                tasks,
                task_stream_map,
                query=query,
                limit=limit,
                include_raw=include_raw,
                config=config,
                query_vector=query_vector,
                vector=self._vector,
                since=since,
                until=until,
            )

    def _append_conversation_tasks(
        self,
        tasks: list[asyncio.Task[list[MemorySearchResult]]],
        task_stream_map: dict[asyncio.Task[Any], str],
        *,
        query: str,
        limit: int,
        include_raw: bool,
        config: MemoryConfig,
        query_vector: list[float],
        vector: VectorStoreProtocol,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> None:
        if self._config.retrieval.enable_two_pass_assistant_retrieval and is_assistant_reference_query(query):
            get_search_metrics().record_assistant_reference_query()
            use_dual = self._should_use_dual_channel(query)
            query_raw = query_vector if use_dual else None
            t = asyncio.create_task(
                search_conversation_two_pass(
                    query_raw or query_vector,
                    query_vector,
                    query,
                    limit,
                    vector,
                    config,
                    namespaces=self._namespaces,
                    include_raw=include_raw,
                    since=since,
                    until=until,
                )
            )
            tasks.append(t)
            task_stream_map[t] = "conversation"
            return

        use_dual = self._should_use_dual_channel(query)
        query_raw = query_vector if use_dual else None
        t = asyncio.create_task(
            search_conversation(
                query_raw,
                query_vector,
                limit,
                vector,
                config,
                namespaces=self._namespaces,
                include_raw=include_raw,
                since=since,
                until=until,
            )
        )
        tasks.append(t)
        task_stream_map[t] = "conversation"

    def _should_use_dual_channel(self, query: str) -> bool:
        if not self._config.retrieval.enable_adaptive_channel:
            return True
        return should_use_dual_channel(query, self._config.retrieval)
