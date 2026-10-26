"""Write denial for the subagent memory view: every mutating ``MemoryManager`` method raises ``PermissionError``.

[INPUT]
- memory.types::AnyMemory and the memory models (POS: signatures the denials keep identical to the base class)
- memory._manager.reindex::ReindexResult, ProgressCallback (POS: reindex result and callback types)

[OUTPUT]
- DeniedMemoryWrites: mixin whose every override denies the write, with the base class signature

[POS]
Subagent isolation, write half of ``ReadOnlyMemoryView``. A caller written against ``MemoryManager`` keeps
working until it writes, so each override keeps the base signature. A new mutating method on
``MemoryManager`` is added here with ``_deny()``; ``tests/toolkits/memory/test_read_only_view_surface.py``
fails until it is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, NoReturn

from myrm_agent_harness.toolkits.memory.types import (
    ARCHIVE_RETENTION_DAYS,
    AnyMemory,
    EpisodicMemory,
    MemoryMutationResult,
    MemoryStatus,
    MemoryType,
    PendingResolutionAction,
    ProceduralMemory,
    RuleSource,
    SemanticMemory,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from myrm_agent_harness.infra.cooperative_signals import CooperativePauseSignal
    from myrm_agent_harness.toolkits.memory._internal.scope import MemoryWriteTarget
    from myrm_agent_harness.toolkits.memory._manager.reindex import ProgressCallback, ReindexResult
    from myrm_agent_harness.toolkits.memory.backup import (
        BackupResult,
        MemoryBackupStrategy,
        RestoreResult,
    )
    from myrm_agent_harness.toolkits.memory.health import MaintenanceReport


class DeniedMemoryWrites:
    """Every write or mutation raises ``PermissionError``; reads live on ``ReadOnlyMemoryView``."""

    def _deny(self) -> NoReturn:
        raise PermissionError(
            "ReadOnlyMemoryView: write operations are forbidden in a sub-agent "
            "(read-only memory view, READ_ONLY_GLOBAL)."
        )

    async def store(
        self,
        memory: AnyMemory,
        *,
        _bypass_approval: bool = False,
        _force_pending: bool = False,
        _scope_prevalidated: bool = False,
    ) -> AnyMemory:
        self._deny()

    async def store_batch(
        self,
        memories: Sequence[AnyMemory],
        *,
        _bypass_approval: bool = False,
        _force_pending: bool = False,
        _skip_dedup: bool = False,
    ) -> list[AnyMemory]:
        self._deny()

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

    async def delete_memory(self, collection: str, ids: list[str], *, allow_protected: bool = True) -> int:
        self._deny()

    async def delete_memory_by_id(self, memory_id: str) -> int:
        self._deny()

    async def delete_rule(self, rule_id: str, *, allow_protected: bool = True) -> bool:
        self._deny()

    async def purge_expired_archived_memories(self, *, ttl_days: int = ARCHIVE_RETENTION_DAYS) -> int:
        self._deny()

    async def purge_expired_archived_rules(self, *, ttl_days: int = ARCHIVE_RETENTION_DAYS) -> int:
        self._deny()

    async def delete_all(self) -> dict[str, int]:
        self._deny()

    async def delete_by_type(self, memory_type: MemoryType, *, include_previous_models: bool = True) -> int:
        self._deny()

    async def delete_profile(self, key_or_id: str) -> bool:
        self._deny()

    async def correct_memory(
        self, memory_id: str, corrected_content: str, *, allow_protected: bool = True
    ) -> SemanticMemory:
        self._deny()

    async def restore_backup(
        self, backup_id: str, strategy: MemoryBackupStrategy, *, overwrite: bool = False
    ) -> RestoreResult:
        self._deny()

    async def delete_backup(self, backup_id: str, strategy: MemoryBackupStrategy) -> bool:
        self._deny()

    async def run_maintenance_cycle(
        self, *, force: bool = False, pause_signal: CooperativePauseSignal | None = None
    ) -> MaintenanceReport:
        self._deny()

    async def set_profile_attribute(self, key: str, value: str, *, _force_pending: bool = False) -> str | None:
        self._deny()

    async def approve(self, pending_id: str, *, edited_content: str | None = None) -> AnyMemory | None:
        self._deny()

    async def reject(self, pending_id: str) -> None:
        self._deny()

    async def batch_approve(self, pending_ids: list[str]) -> tuple[int, list[str]]:
        self._deny()

    async def batch_reject(self, pending_ids: list[str]) -> int:
        self._deny()

    async def rate_memory(self, memory_id: str, score: int, collection: str | None = None) -> bool:
        self._deny()

    async def pin_memory(self, memory_id: str) -> AnyMemory:
        self._deny()

    async def unpin_memory(self, memory_id: str) -> AnyMemory:
        self._deny()

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

    async def create_backup(self, strategy: MemoryBackupStrategy, description: str | None = None) -> BackupResult:
        self._deny()

    async def import_memories(
        self, data: dict[str, list[dict[str, object]]], *, skip_duplicates: bool = True
    ) -> dict[str, int]:
        self._deny()

    async def submit_pending(
        self,
        memory: AnyMemory,
        *,
        resolution_action: PendingResolutionAction = PendingResolutionAction.STORE,
        target_memory_id: str | None = None,
        target_content: str | None = None,
    ) -> str:
        self._deny()

    async def add_pitfall(
        self,
        content: str,
        *,
        failure_reason: str,
        negative_lesson: str,
        subtask_phase: Literal["analyze", "locate", "edit", "verify"] | None = None,
        confidence_tier: Literal["strong", "weak", "shadow"] = "strong",
        related_entities: list[str] | None = None,
        source_chat_id: str | None = None,
        source_message_id: str | None = None,
        write_target: MemoryWriteTarget = "bound",
    ) -> EpisodicMemory:
        self._deny()

    async def check_session_recurrence(self, session_summary: str) -> None:
        self._deny()

    async def delete_memories_by_ids(self, memory_ids_by_type: dict[str, list[str]]) -> MemoryMutationResult:
        self._deny()

    async def delete_memories_by_metadata(
        self, metadata_key: str, metadata_value: str, *, memory_types: Sequence[MemoryType] | None = None
    ) -> dict[str, int]:
        self._deny()

    async def delete_system_profile_attribute(self, key: str) -> bool:
        self._deny()

    async def purge_by_source_chat_id(self, chat_id: str) -> dict[str, int]:
        self._deny()

    async def reindex_from_orphans(self, *, progress_cb: ProgressCallback | None = None) -> ReindexResult:
        self._deny()

    async def restore_profile_attributes(self, values: dict[str, str | None]) -> int:
        self._deny()

    async def set_system_profile_attribute(self, key: str, value: str) -> None:
        self._deny()

    async def sparse_mutate_memory(
        self, memory_id: str, patch_content: str, *, allow_protected: bool = False
    ) -> SemanticMemory:
        self._deny()
