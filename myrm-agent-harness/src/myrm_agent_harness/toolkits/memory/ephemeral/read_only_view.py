"""Read-only view over a parent MemoryManager: the only memory a sub-agent gets.

[INPUT]
- memory.manager::MemoryManager (POS: base class whose public surface the view mirrors)
- ephemeral.denied_writes::DeniedMemoryWrites (POS: write half, every mutation raises PermissionError)

[OUTPUT]
- ReadOnlyMemoryView: reads delegate to the parent, every write raises PermissionError

[POS]
Subagent isolation. Every MemoryIsolationPolicy resolves to this view: memory tools are bound to the parent
manager and cannot be redirected, so a child is limited to reading the parent's memory. Each override keeps
the base class signature so a caller written against MemoryManager works unchanged.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.ephemeral.denied_writes import DeniedMemoryWrites
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import (
    AnyMemory,
    MemorySearchResult,
    MemoryType,
    PendingRecord,
    ProfileAttributeSnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from pathlib import Path

    from myrm_agent_harness.toolkits.memory._manager.reindex import OrphanCollectionInfo, ReindexEstimate
    from myrm_agent_harness.toolkits.memory.backup import BackupMetadata, MemoryBackupStrategy
    from myrm_agent_harness.toolkits.memory.health import HealthScore
    from myrm_agent_harness.toolkits.memory.observability import MemoryRetrievalTrace
    from myrm_agent_harness.toolkits.memory.session import MemorySession


class ReadOnlyMemoryView(DeniedMemoryWrites, MemoryManager):
    """Read-only proxy over a parent MemoryManager.

    Reads delegate to the parent; every write or mutation raises PermissionError (``DeniedMemoryWrites``).
    No backend is attached, so a base-class method the view does not override would fail by accident
    instead of by policy. ``tests/toolkits/memory/test_read_only_view_surface.py`` requires every public
    ``MemoryManager`` member to be classified here or in ``DeniedMemoryWrites``.
    """

    def __init__(self, parent: MemoryManager) -> None:
        self._parent = parent
        self._user_id = parent.user_id
        self._namespaces = parent.namespaces
        self._scope = parent.scope
        self._config = parent.config
        self._active_session = None
        self._approval_required = False
        self._last_cited_memory_ids: list[str] = []
        self._memory_policy = parent.memory_policy
        self._recall_mode = parent.recall_mode

        self._consolidation_llm = None
        self._maintenance_lock = asyncio.Lock()
        self._vector = None
        self._relational = None
        self._graph = None

    # ── Read operations (delegated) ──────────────────────────────────

    async def search(
        self,
        query: str,
        *,
        memory_types: list[MemoryType] | None = None,
        limit: int = 10,
        use_rrf: bool = True,
        include_raw: bool = False,
        since: datetime | None = None,
        until: datetime | None = None,
        track_access: bool = True,
        dynamic_signal_weights: dict[str, float] | None = None,
    ) -> list[MemorySearchResult]:
        return await self._parent.search(
            query,
            memory_types=memory_types,
            limit=limit,
            use_rrf=use_rrf,
            include_raw=include_raw,
            since=since,
            until=until,
            track_access=track_access,
            dynamic_signal_weights=dynamic_signal_weights,
        )

    async def get_context(
        self,
        *,
        include_profile: bool = True,
        include_rules: bool = True,
        include_agent_instructions: bool = True,
    ) -> dict[str, object]:
        return await self._parent.get_context(
            include_profile=include_profile,
            include_rules=include_rules,
            include_agent_instructions=include_agent_instructions,
        )

    async def get_learned_context(self) -> dict[str, list[dict[str, str]]]:
        return await self._parent.get_learned_context()

    async def get_memory(self, memory_id: str) -> AnyMemory | None:
        return await self._parent.get_memory(memory_id)

    async def get_profile_attribute_snapshot(self, key: str) -> ProfileAttributeSnapshot:
        return await self._parent.get_profile_attribute_snapshot(key)

    async def count_by_source_chat_id(self, chat_id: str) -> dict[str, int]:
        return await self._parent.count_by_source_chat_id(chat_id)

    async def list_memory_ids_by_metadata(
        self, metadata_key: str, metadata_value: str, *, memory_types: Sequence[MemoryType] | None = None
    ) -> dict[str, list[str]]:
        return await self._parent.list_memory_ids_by_metadata(metadata_key, metadata_value, memory_types=memory_types)

    async def list_memory_refs_by_metadata(
        self, metadata_key: str, metadata_value: str, *, memory_types: Sequence[MemoryType] | None = None
    ) -> dict[str, list[dict[str, str]]]:
        return await self._parent.list_memory_refs_by_metadata(metadata_key, metadata_value, memory_types=memory_types)

    async def check_integrity(self) -> tuple[bool, str]:
        return await self._parent.check_integrity()

    async def detect_orphan_collections(self) -> list[OrphanCollectionInfo]:
        return await self._parent.detect_orphan_collections()

    async def estimate_reindex(self) -> ReindexEstimate:
        return await self._parent.estimate_reindex()

    async def export_markdown(
        self,
        target_dir: str | Path,
        *,
        since_ts: datetime | None = None,
        agent_id: str | None = None,
        memory_types: list[MemoryType] | None = None,
    ) -> dict[str, int]:
        return await self._parent.export_markdown(
            target_dir, since_ts=since_ts, agent_id=agent_id, memory_types=memory_types
        )

    async def export_rules_safe(
        self,
        *,
        agent_id: str | None = None,
        rule_ids: list[str] | None = None,
        output_format: str = "markdown",
    ) -> list[dict[str, object]]:
        return await self._parent.export_rules_safe(agent_id=agent_id, rule_ids=rule_ids, output_format=output_format)

    def begin_session(self, chat_id: str) -> MemorySession:
        return self._parent.begin_session(chat_id)

    async def end_session(self) -> list[AnyMemory]:
        return []

    @property
    def namespaces(self) -> list[str]:
        return self._namespaces

    @property
    def has_relational(self) -> bool:
        return self._parent.has_relational

    @property
    def has_vector(self) -> bool:
        return self._parent.has_vector

    @property
    def has_graph(self) -> bool:
        return self._parent.has_graph

    @property
    def has_vector_store(self) -> bool:
        return self._parent.has_vector_store

    @property
    def vector_is_persistent(self) -> bool:
        return self._parent.vector_is_persistent

    @property
    def last_retrieval_trace(self) -> MemoryRetrievalTrace | None:
        return self._parent.last_retrieval_trace

    def set_last_cited_memory_ids(self, ids: list[str]) -> None:
        self._last_cited_memory_ids = ids

    async def close(self) -> None:
        pass

    # ── Read operations that lack internal deps — return safe defaults ──

    async def get_profile_attribute(self, key: str) -> str | None:
        return await self._parent.get_profile_attribute(key)

    async def get_pending(self, pending_id: str) -> PendingRecord | None:
        return None

    async def list_pending(self, *, limit: int = 50) -> list[PendingRecord]:
        return []

    async def count_pending(self) -> int:
        return 0

    async def list_memories(
        self,
        memory_type: MemoryType,
        *,
        limit: int = 100,
        offset: int = 0,
        include_archived: bool = False,
        sort_by: str | None = None,
        sort_order: str = "desc",
        tag_filter: str | None = None,
    ) -> list[AnyMemory]:
        return await self._parent.list_memories(
            memory_type,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
            sort_by=sort_by,
            sort_order=sort_order,
            tag_filter=tag_filter,
        )

    async def count_memories(
        self, memory_type: MemoryType, *, since: datetime | None = None, tag_filter: str | None = None
    ) -> int:
        return await self._parent.count_memories(memory_type, since=since, tag_filter=tag_filter)

    async def list_backups(self, strategy: MemoryBackupStrategy) -> list[BackupMetadata]:
        return await strategy.list_backups()

    async def export_all(self) -> dict[str, list[dict[str, object]]]:
        return await self._parent.export_all()

    def get_enabled_types(self) -> list[MemoryType]:
        return self._parent.get_enabled_types()

    async def compute_health_score(self) -> HealthScore:
        return await self._parent.compute_health_score()
