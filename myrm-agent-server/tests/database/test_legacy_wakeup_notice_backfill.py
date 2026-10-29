"""A user row with a ``wakeup_<task id>`` id and no marker gets the followup marker, once and only on its own rows.

The wake each such notice started always ran, so the backfill marks it as a followup notice; nothing a person or the
agent wrote changes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database.migrations import BACKFILL_LEGACY_WAKEUP_NOTICE_SQL, MIGRATION_STATEMENTS
from app.database.models.base import Base

_NOW = datetime.now(UTC).isoformat()

# (id, role, extra_data as stored) -> what the row holds after the backfill
_ROWS: list[tuple[str, str, str | None]] = [
    ("wakeup_task-1", "user", None),
    ("wakeup_task-2", "user", "null"),
    ("wakeup_task-3", "user", '{"spillover": {"preview": "x"}}'),
    ("wakeup_followup_task-4", "user", '{"wakeup_notice": "followup"}'),
    ("wakeup_degraded_task-5", "user", '{"wakeup_notice": "degraded"}'),
    ("wakeup_task-6", "assistant", None),
    ("person-7", "user", None),
    ("wakeupish-8", "user", None),
    ("Wakeup_task-9", "user", None),
]


def test_the_backfill_is_a_registered_migration() -> None:
    assert BACKFILL_LEGACY_WAKEUP_NOTICE_SQL in MIGRATION_STATEMENTS


@pytest.mark.asyncio
async def test_only_unmarked_notice_rows_get_the_followup_marker_and_a_replay_changes_nothing() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        chats, messages = Base.metadata.tables["chats"], Base.metadata.tables["messages"]
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[chats, messages]))
        await conn.execute(chats.insert().values(id="c1", action_mode="fast"))
        for message_id, role, extra in _ROWS:
            await conn.execute(
                text(
                    "INSERT INTO messages (id, chat_id, role, content, sent_at, sent_timezone, created_at, extra_data, is_active) "
                    "VALUES (:id, 'c1', :role, 'x', :now, 'UTC', :now, :extra, 1)"
                ),
                {"id": message_id, "role": role, "now": _NOW, "extra": extra},
            )

        await conn.execute(text(BACKFILL_LEGACY_WAKEUP_NOTICE_SQL))
        after_first = (await conn.execute(text("SELECT id, extra_data FROM messages ORDER BY id"))).all()
        await conn.execute(text(BACKFILL_LEGACY_WAKEUP_NOTICE_SQL))
        after_replay = (await conn.execute(text("SELECT id, extra_data FROM messages ORDER BY id"))).all()
    await engine.dispose()

    stored = {row.id: (json.loads(row.extra_data) if row.extra_data is not None else None) for row in after_first}
    assert stored == {
        "wakeup_task-1": {"wakeup_notice": "followup"},
        "wakeup_task-2": {"wakeup_notice": "followup"},
        "wakeup_task-3": {"spillover": {"preview": "x"}, "wakeup_notice": "followup"},
        "wakeup_followup_task-4": {"wakeup_notice": "followup"},
        "wakeup_degraded_task-5": {"wakeup_notice": "degraded"},
        "wakeup_task-6": None,
        "person-7": None,
        "wakeupish-8": None,
        "Wakeup_task-9": None,
    }
    assert after_replay == after_first
