"""Dream Diary and Grounded Dreaming business service.

Manages the persistence, feedback lifecycle, and execution of Grounded Dreaming
cycles and surgical precision unlearning on session-derived memories.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Awaitable, Callable, Sequence
from typing import Mapping

from myrm_agent_harness.toolkits.memory import (
    DreamDiaryEntry,
    DreamDiaryStatus,
    DreamSessionFragment,
    GroundedDreamingEngine,
    SurgicalSessionMemoryUnlearner,
    SurgicalUnlearnReport,
)

logger = logging.getLogger(__name__)


class DreamDiaryService:
    """Service orchestrating idle-time grounded dreaming and surgical unlearning."""

    def __init__(self, engine: GroundedDreamingEngine | None = None) -> None:
        self._engine = engine or GroundedDreamingEngine()
        self._entries: dict[str, DreamDiaryEntry] = {}
        self._lock = threading.Lock()

    def get_entries(
        self,
        status: DreamDiaryStatus | None = None,
        limit: int = 50,
    ) -> list[DreamDiaryEntry]:
        """Retrieve dream diary entries, optionally filtered by status and sorted by timestamp."""
        with self._lock:
            all_entries = list(self._entries.values())

        if status is not None:
            filtered = [e for e in all_entries if e.status == status]
        else:
            filtered = all_entries

        # Sort newest first
        filtered.sort(key=lambda e: e.created_at, reverse=True)
        return filtered[:limit]

    def get_entry(self, entry_id: str) -> DreamDiaryEntry | None:
        """Fetch a single dream diary entry by identifier."""
        with self._lock:
            return self._entries.get(entry_id)

    def record_dream_cycle(
        self,
        fragments: Sequence[DreamSessionFragment],
    ) -> list[DreamDiaryEntry]:
        """Execute dreaming cycle over session fragments and persist generated diary entries."""
        new_entries = self._engine.process_fragments(fragments)
        with self._lock:
            for entry in new_entries:
                self._entries[entry.entry_id] = entry
        logger.info("Recorded %d new dream diary entries", len(new_entries))
        return new_entries

    def submit_feedback(
        self,
        entry_id: str,
        action: str,
        reason: str | None = None,
    ) -> DreamDiaryEntry | None:
        """Submit user review feedback (accept / reject) on a dream diary entry."""
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
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

        # Also purge or invalidate dream diary entries citing only this session
        with self._lock:
            for entry in list(self._entries.values()):
                if entry.source_session_ids == [session_id]:
                    entry.status = DreamDiaryStatus.REJECTED
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
