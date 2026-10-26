"""Read-only view over a parent MemoryManager for READ_ONLY_GLOBAL subagents.

[INPUT]
- memory.manager::MemoryManager (POS: base class whose public surface the view mirrors)

[OUTPUT]
- ReadOnlyMemoryView: reads delegate to the parent, every write raises PermissionError

[POS]
Subagent isolation, read-only strategy. Each override keeps the base class signature so a
caller written against MemoryManager works unchanged.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Literal

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import (
    ARCHIVE_RETENTION_DAYS,
    AnyMemory,
    EpisodicMemory,
    MemorySearchResult,
    MemoryStatus,
    MemoryType,
    PendingRecord,
    PendingResolutionAction,
    ProceduralMemory,
    RuleSource,
    SemanticMemory,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from myrm_agent_harness.infra.cooperative_signals import CooperativePauseSignal
    from myrm_agent_harness.toolkits.memory.backup import (
        BackupMetadata,
        BackupResult,
        MemoryBackupStrategy,
        RestoreResult,
    )
    from myrm_agent_harness.toolkits.memory.health import HealthScore, MaintenanceReport
    from myrm_agent_harness.toolkits.memory.session import MemorySession


class ReadOnlyMemoryView(MemoryManager):
    """Read-only proxy over a parent MemoryManager.

    Delegates all read operations (search, get_context, get_memory, etc.) to
    the parent.  Every write/mutate operation unconditionally raises
    PermissionError, providing type-system-level enforcement of the
    READ_ONLY_GLOBAL isolation policy — even if new write tools or code paths
    are added in the future. When a new write method lands on MemoryManager,
    override it here with ``_deny()`` so the invariant stays intact.
    """

    def __init__(self, parent: MemoryManager) -> None:
        self._parent = parent
        self._user_id = parent._user_id
        self._namespaces = parent._namespaces
        self._scope = parent._scope
        self._config = parent._config
        self._active_session = None
        self._approval_required = False
        self._last_cited_memory_ids: list[str] = []
        self._memory_policy = parent._memory_policy
        self._recall_mode = parent._recall_mode

        self._consolidation_llm = None
        self._maintenance_lock = asyncio.Lock()
        self._vector = None
        self._relational = None
        self._graph = None

    def _deny(self) -> None:
        raise PermissionError(
            "ReadOnlyMemoryView: write operations are forbidden under READ_ONLY_GLOBAL isolation policy."
        )

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

    # ── Write operations (all denied) ────────────────────────────────

    async def store(
        self,
        memory: AnyMemory,
        *,
        _bypass_approval: bool = False,
        _force_pending: bool = False,
        _scope_prevalidated: bool = False,
    ) -> AnyMemory:
        self._deny()
        return memory  # unreachable, satisfies type checker

    async def store_batch(
        self, memories: Sequence[AnyMemory], *, _bypass_approval: bool = False, _force_pending: bool = False
    ) -> list[AnyMemory]:
        self._deny()
        return []

    async def add_knowledge(
        self,
        content: str,
        *,
        importance: float = 0.5,
        tags: list[str] | None = None,
        source_chat_id: str | None = None,
        write_target: Literal["bound", "shared"] = "bound",
    ) -> SemanticMemory:
        self._deny()
        raise AssertionError  # unreachable

    async def add_event(
        self,
        content: str,
        *,
        event_type: str = "conversation",
        related_entities: list[str] | None = None,
        source_chat_id: str | None = None,
        source_message_id: str | None = None,
        subtask_phase: Literal["analyze", "locate", "edit", "verify"] | None = None,
        is_failure_attempt: bool = False,
        failure_reason: str | None = None,
        negative_lesson: str | None = None,
        confidence_tier: Literal["strong", "weak", "shadow"] = "strong",
        write_target: Literal["bound", "shared"] = "bound",
    ) -> EpisodicMemory:
        self._deny()
        raise AssertionError  # unreachable

    async def add_rule(
        self,
        trigger: str,
        action: str,
        *,
        priority: int = 0,
        trigger_keywords: list[str] | None = None,
        source: RuleSource = RuleSource.USER_EXTRACTED,
    ) -> ProceduralMemory:
        self._deny()
        raise AssertionError  # unreachable

    async def delete_memory(self, collection: str, ids: list[str], *, allow_protected: bool = True) -> int:
        self._deny()
        return 0

    async def delete_memory_by_id(self, memory_id: str) -> int:
        self._deny()
        return 0

    async def delete_rule(self, rule_id: str, *, allow_protected: bool = True) -> bool:
        self._deny()
        return False

    async def purge_expired_archived_memories(self, *, ttl_days: int = ARCHIVE_RETENTION_DAYS) -> int:
        self._deny()
        return 0

    async def purge_expired_archived_rules(self, *, ttl_days: int = ARCHIVE_RETENTION_DAYS) -> int:
        self._deny()
        return 0

    async def delete_all(self) -> dict[str, int]:
        self._deny()
        return {}

    async def delete_by_type(self, memory_type: MemoryType, *, include_previous_models: bool = True) -> int:
        self._deny()
        return 0

    async def delete_profile(self, key_or_id: str) -> bool:
        self._deny()
        return False

    async def correct_memory(
        self, memory_id: str, corrected_content: str, *, allow_protected: bool = True
    ) -> SemanticMemory:
        self._deny()
        raise AssertionError  # unreachable

    async def restore_backup(
        self, backup_id: str, strategy: MemoryBackupStrategy, *, overwrite: bool = False
    ) -> RestoreResult:
        self._deny()
        raise AssertionError  # unreachable

    async def delete_backup(self, backup_id: str, strategy: MemoryBackupStrategy) -> bool:
        self._deny()
        return False

    async def run_maintenance_cycle(
        self, *, force: bool = False, pause_signal: CooperativePauseSignal | None = None
    ) -> MaintenanceReport:
        self._deny()
        raise AssertionError  # unreachable

    async def set_profile_attribute(self, key: str, value: str, *, _force_pending: bool = False) -> str | None:
        self._deny()
        return None

    async def approve(self, pending_id: str, *, edited_content: str | None = None) -> AnyMemory | None:
        self._deny()
        return None

    async def reject(self, pending_id: str) -> None:
        self._deny()

    async def batch_approve(self, pending_ids: list[str]) -> tuple[int, list[str]]:
        self._deny()
        return (0, [])

    async def batch_reject(self, pending_ids: list[str]) -> int:
        self._deny()
        return 0

    async def rate_memory(self, memory_id: str, score: int, collection: str | None = None) -> bool:
        self._deny()
        return False

    async def pin_memory(self, memory_id: str) -> AnyMemory:
        self._deny()
        raise AssertionError  # unreachable

    async def unpin_memory(self, memory_id: str) -> AnyMemory:
        self._deny()
        raise AssertionError  # unreachable

    async def update_memory(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        importance: float | None = None,
        confidence: float | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, str | int | float | bool] | None = None,
        is_active: bool | None = None,
        status: MemoryStatus | None = None,
        reasoning: str | None = None,
        application: str | None = None,
        is_user_locked: bool | None = None,
        is_exact_fact: bool | None = None,
        allow_protected: bool = True,
    ) -> AnyMemory:
        self._deny()
        raise AssertionError  # unreachable

    async def create_backup(self, strategy: MemoryBackupStrategy, description: str | None = None) -> BackupResult:
        self._deny()
        raise AssertionError  # unreachable

    async def import_memories(
        self, data: dict[str, list[dict[str, object]]], *, skip_duplicates: bool = True
    ) -> dict[str, int]:
        self._deny()
        return {}

    async def submit_pending(
        self,
        memory: AnyMemory,
        *,
        resolution_action: PendingResolutionAction = PendingResolutionAction.STORE,
        target_memory_id: str | None = None,
        target_content: str | None = None,
    ) -> str:
        self._deny()
        return ""

    def set_last_cited_memory_ids(self, ids: list[str]) -> None:
        self._last_cited_memory_ids = ids

    async def close(self) -> None:
        pass

    # ── Read operations that lack internal deps — return safe defaults ──

    async def get_profile_attribute(self, key: str) -> str | None:
        return await self._parent.get_profile_attribute(key)

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
