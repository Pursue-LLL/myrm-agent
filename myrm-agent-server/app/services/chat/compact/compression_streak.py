"""Chat DB-backed compression ineffective streak store.

[INPUT]
- app.config.settings::settings.database.sqlite_path (POS: SQLite file path)
- app.database.models::Chat (POS: compression_ineffective_streak column)

[OUTPUT]
- ChatCompressionStreakStore: harness CompressionStreakStore via sync SQLite
- register_chat_compression_streak_store: register at app startup
- load/save async helpers for compact_chat transactional paths

[POS]
Server product persistence for anti-thrash streak (Hermes compression_ineffective_count parity).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat

logger = logging.getLogger(__name__)


def _sqlite_path() -> Path:
    from app.config.settings import settings

    return Path(os.path.expanduser(settings.database.sqlite_path))


class ChatCompressionStreakStore:
    """Sync SQLite streak store for harness guard (CompressProcessor + compact_chat)."""

    def __init__(self) -> None:
        self._cache: dict[str, int] = {}

    def get_streak(self, chat_id: str | None) -> int:
        if not chat_id:
            return 0
        if chat_id in self._cache:
            streak = self._cache[chat_id]
            self._mirror_task_metrics(chat_id, streak)
            return streak
        streak = self._read_sqlite(chat_id)
        self._cache[chat_id] = streak
        self._mirror_task_metrics(chat_id, streak)
        return streak

    def set_streak(self, chat_id: str | None, streak: int) -> None:
        if not chat_id:
            return
        normalized = max(0, int(streak))
        self._cache[chat_id] = normalized
        self._write_sqlite(chat_id, normalized)
        self._mirror_task_metrics(chat_id, normalized)

    def seed_streak(self, chat_id: str, streak: int) -> None:
        """Seed in-process streak without writing SQLite (same-transaction hydrate)."""
        normalized = max(0, int(streak))
        self._cache[chat_id] = normalized
        self._mirror_task_metrics(chat_id, normalized)

    def _read_sqlite(self, chat_id: str) -> int:
        db_path = _sqlite_path()
        if not db_path.exists():
            return 0
        try:
            with sqlite3.connect(db_path, timeout=5.0) as conn:
                row = conn.execute(
                    "SELECT compression_ineffective_streak FROM chats WHERE id = ?",
                    (chat_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            logger.warning(
                "Compression streak read failed for chat %s: %s", chat_id, exc
            )
            return 0
        if row is None or row[0] is None:
            return 0
        return max(0, int(row[0]))

    def _write_sqlite(self, chat_id: str, streak: int) -> None:
        db_path = _sqlite_path()
        if not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(db_path, timeout=5.0) as conn:
                conn.execute(
                    "UPDATE chats SET compression_ineffective_streak = ? WHERE id = ?",
                    (streak, chat_id),
                )
                conn.commit()
        except sqlite3.Error as exc:
            logger.warning(
                "Compression streak write failed for chat %s: %s", chat_id, exc
            )

    @staticmethod
    def _mirror_task_metrics(chat_id: str, streak: int) -> None:
        from myrm_agent_harness.agent.context_management.tracking.task_metrics import (
            get_or_create_task_metrics,
        )

        metrics = get_or_create_task_metrics(chat_id)
        if metrics is not None:
            metrics.compression_ineffective_streak = streak


def register_chat_compression_streak_store() -> None:
    """Register DB-backed streak store for harness anti-thrash guard."""
    from myrm_agent_harness.agent.context_management.strategies.compression.compression_streak_store import (
        register_compression_streak_store,
    )

    register_compression_streak_store(ChatCompressionStreakStore())


async def load_compression_ineffective_streak(db: AsyncSession, chat_id: str) -> int:
    """Load streak from Chat row (async ORM path)."""
    row = await db.execute(
        select(Chat.compression_ineffective_streak).where(Chat.id == chat_id)
    )
    value = row.scalar_one_or_none()
    if value is None:  # pragma: no cover - column has server_default=0, never NULL in DB
        return 0
    return max(0, int(value))


async def save_compression_ineffective_streak(
    db: AsyncSession,
    chat_id: str,
    streak: int,
) -> None:
    """Persist streak on Chat row within caller transaction."""
    normalized = max(0, int(streak))
    await db.execute(
        update(Chat)
        .where(Chat.id == chat_id)
        .values(compression_ineffective_streak=normalized)
    )
    await db.flush()
    ChatCompressionStreakStore._mirror_task_metrics(chat_id, normalized)
    from myrm_agent_harness.agent.context_management.strategies.compression.compression_streak_store import (
        get_compression_streak_store,
    )

    store = get_compression_streak_store()
    if isinstance(store, ChatCompressionStreakStore):
        store.seed_streak(chat_id, normalized)


async def hydrate_compression_streak_from_db(db: AsyncSession, chat_id: str) -> int:
    """Load DB streak into active store before anti-thrash evaluation."""
    streak = await load_compression_ineffective_streak(db, chat_id)
    from myrm_agent_harness.agent.context_management.strategies.compression.compression_streak_store import (
        get_compression_streak_store,
    )

    store = get_compression_streak_store()
    if isinstance(store, ChatCompressionStreakStore):
        store.seed_streak(chat_id, streak)
    else:
        store.set_streak(chat_id, streak)
    return streak
