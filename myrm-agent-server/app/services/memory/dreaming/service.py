"""Dream Diary and Grounded Dreaming business service.

[POS]
记忆系统认知成长与遗忘治理服务。连接底层 Grounded Dreaming 跨会话聚类蒸馏、
梦境日记审查流转、消息级双向溯源反查、条目锁定防遗忘、一键撤回彻底抹除、
人工纠偏事实陈述，以及外科手术式会话记忆精准拔除。

[INPUT]
- myrm_agent_harness.toolkits.memory::DreamDiaryEntry (POS: 梦境日记认知条目强类型)
- myrm_agent_harness.toolkits.memory::DreamDiaryStatus (POS: 日记审核状态枚举)
- myrm_agent_harness.toolkits.memory::DreamSessionFragment (POS: 会话碎片数据契约)
- myrm_agent_harness.toolkits.memory::DreamingTriggerReason (POS: 做梦触发动因枚举)
- myrm_agent_harness.toolkits.memory::GroundedDreamingEngine (POS: 闲时跨会话做梦聚类引擎)
- myrm_agent_harness.toolkits.memory::GroundedDreamingScheduler (POS: 闲时做梦自主调度器)
- myrm_agent_harness.toolkits.memory::MemoryProvenanceAnchor (POS: 消息级双向溯源锚点)
- myrm_agent_harness.toolkits.memory::SurgicalSessionMemoryUnlearner (POS: 外科手术式会话记忆遗忘算子)
- myrm_agent_harness.toolkits.memory::SurgicalUnlearnReport (POS: 外科手术式遗忘审计报告)

[OUTPUT]
- DreamDiaryService: 梦境日记持久化与用户全生命周期治理业务服务
- get_dream_diary_service: 全局单例工厂方法
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Awaitable, Callable, Sequence
from typing import Mapping

from myrm_agent_harness.toolkits.memory import (
    DreamDiaryEntry,
    DreamDiaryStatus,
    DreamingTriggerReason,
    DreamSessionFragment,
    GroundedDreamingEngine,
    GroundedDreamingScheduler,
    MemoryProvenanceAnchor,
    SurgicalSessionMemoryUnlearner,
    SurgicalUnlearnReport,
)

logger = logging.getLogger(__name__)


class DreamDiaryService:
    """Service orchestrating idle-time grounded dreaming and surgical unlearning."""

    def __init__(
        self,
        engine: GroundedDreamingEngine | None = None,
        scheduler: GroundedDreamingScheduler | None = None,
    ) -> None:
        self._engine = engine or GroundedDreamingEngine()
        self._scheduler = scheduler or GroundedDreamingScheduler(engine=self._engine)
        self._entries: dict[str, DreamDiaryEntry] = {}
        self._lock = threading.Lock()

    def get_entries(
        self,
        status: DreamDiaryStatus | None = None,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[DreamDiaryEntry]:
        """Retrieve dream diary entries, optionally filtered by status/project and sorted newest first."""
        with self._lock:
            all_entries = list(self._entries.values())

        filtered = all_entries
        if status is not None:
            filtered = [e for e in filtered if e.status == status]
        if project_id is not None:
            filtered = [e for e in filtered if e.project_id == project_id or e.project_id is None]

        filtered.sort(key=lambda e: e.created_at, reverse=True)
        return filtered[:limit]

    def get_entry(self, entry_id: str) -> DreamDiaryEntry | None:
        """Fetch a single dream diary entry by identifier."""
        with self._lock:
            return self._entries.get(entry_id)

    def get_entry_provenance(self, entry_id: str) -> list[MemoryProvenanceAnchor] | None:
        """Retrieve immutable message-level provenance anchors for a specific dream entry."""
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                return None
            return list(entry.provenance_anchors)

    def record_dream_cycle(
        self,
        fragments: Sequence[DreamSessionFragment],
        target_project_id: str | None = None,
    ) -> list[DreamDiaryEntry]:
        """Execute dreaming cycle over session fragments and persist generated diary entries."""
        new_entries = self._engine.process_fragments(fragments, target_project_id=target_project_id)
        with self._lock:
            for entry in new_entries:
                self._entries[entry.entry_id] = entry
        logger.info("Recorded %d new dream diary entries", len(new_entries))
        return new_entries

    def trigger_scheduler(
        self,
        reason: str,
        fragments: Sequence[DreamSessionFragment],
        target_project_id: str | None = None,
        lookback_days: int = 7,
    ) -> list[DreamDiaryEntry]:
        """Trigger idle consolidation or REM backfill via scheduler."""
        norm_reason = reason.strip().lower()
        trigger_enum = DreamingTriggerReason.MANUAL
        if norm_reason in DreamingTriggerReason._value2member_map_:
            trigger_enum = DreamingTriggerReason(norm_reason)

        if trigger_enum == DreamingTriggerReason.REM_BACKFILL:
            entries = self._scheduler.run_rem_backfill(
                historical_fragments=fragments,
                lookback_days=lookback_days,
                target_project_id=target_project_id,
            )
        else:
            entries = self._scheduler.consolidate(
                fragments=fragments,
                trigger_reason=trigger_enum,
                target_project_id=target_project_id,
            )

        with self._lock:
            for entry in entries:
                self._entries[entry.entry_id] = entry
        return entries

    def submit_feedback(
        self,
        entry_id: str,
        action: str,
        reason: str | None = None,
    ) -> DreamDiaryEntry | None:
        """Submit user review feedback (accept / reject) on a dream diary entry."""
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None or entry.is_locked:
                return None

            normalized_action = action.strip().lower()
            if normalized_action in ("accept", "accepted"):
                entry.status = DreamDiaryStatus.ACCEPTED
                entry.rejection_reason = None
            elif normalized_action in ("reject", "rejected"):
                entry.status = DreamDiaryStatus.REJECTED
                entry.rejection_reason = reason
            else:
                logger.warning("Unrecognized feedback action '%s' for entry %s", action, entry_id)
                return None

            return entry

    def lock_entry(self, entry_id: str, reason: str | None = None) -> DreamDiaryEntry | None:
        """Permanently lock a dream diary insight to prevent eviction or automatic changes."""
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                return None
            entry.status = DreamDiaryStatus.LOCKED
            entry.is_locked = True
            logger.info("Locked dream diary entry %s: reason=%s", entry_id, reason)
            return entry

    def revoke_entry(self, entry_id: str, reason: str | None = None) -> DreamDiaryEntry | None:
        """Revoke a dream diary insight, evicting it from active recall consideration."""
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                return None
            entry.status = DreamDiaryStatus.REVOKED
            entry.is_locked = False
            entry.rejection_reason = reason or "Revoked by user"
            logger.info("Revoked dream diary entry %s: reason=%s", entry_id, reason)
            return entry

    def amend_entry(self, entry_id: str, amended_statement: str) -> DreamDiaryEntry | None:
        """Amend the factual statement of a dream diary insight with human correction."""
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None or entry.status == DreamDiaryStatus.REVOKED:
                return None
            entry.amended_statement = amended_statement.strip()
            logger.info("Amended dream diary entry %s with new statement", entry_id)
            return entry

    async def unlearn_session(
        self,
        session_id: str,
        memory_items: Sequence[Mapping[str, object]],
        deleter: Callable[[list[str]], Awaitable[int]] | None = None,
        chat_turn_count: int = 0,
    ) -> SurgicalUnlearnReport:
        """Surgically unlearn all long-term memories derived from session_id."""
        report = await SurgicalSessionMemoryUnlearner.unlearn_session(
            session_id=session_id,
            memory_items=memory_items,
            deleter=deleter,
            chat_turn_count=chat_turn_count,
        )

        with self._lock:
            for entry in list(self._entries.values()):
                if entry.source_session_ids == [session_id] and not entry.is_locked:
                    entry.status = DreamDiaryStatus.REVOKED
                    entry.rejection_reason = f"Session {session_id} surgically unlearned"

        logger.info(
            "Completed surgical unlearning for session %s: %d memories purged",
            session_id,
            len(report.unlearned_memory_ids),
        )
        return report


_global_service: DreamDiaryService | None = None
_service_lock = threading.Lock()


def get_dream_diary_service() -> DreamDiaryService:
    """Access the global singleton DreamDiaryService instance."""
    global _global_service
    with _service_lock:
        if _global_service is None:
            _global_service = DreamDiaryService()
        return _global_service
