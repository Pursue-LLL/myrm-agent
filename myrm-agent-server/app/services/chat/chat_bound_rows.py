"""Rows of plain tables that belong to exactly one chat and are erased together with it.

[INPUT]
- sqlalchemy::column, delete, exists, table (POS: schema-free DELETE statements, so this list needs no ORM imports)

[OUTPUT]
- ChatBoundTable: a table and the column that names its chat
- CHAT_BOUND_TABLES: every table whose rows carry a chat's content or act on it, without a foreign key to ``chats``
- delete_trashed_chat_bound_rows: delete the rows of those of the given chats that are in the trash, inside the caller's transaction

[POS]
Single list of the tables that outlive a deleted chat unless they are cleared by hand: chat rows reach their
messages, forks and recall index through foreign keys or the recall service, but these tables only store the
chat id. A leftover is not harmless: a pending commitment quotes the conversation it came from into later turns
of other chats, an approval keeps the command or patch that was proposed. The per-chat permanent delete, the
safe vault purge and the archive scrub of web incognito chats (``instance_archive/table_policy.py``) all read this
list, so a new table is added in one place; the guard test in
``tests/services/chat/test_chat_bound_rows.py`` fails for any table with a chat column that is neither listed
here nor a reviewed exception.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from sqlalchemy import column, delete, exists, table
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

# SQLite caps the number of bound parameters per statement; stay far below any build's limit.
_BATCH_SIZE = 500

_CHATS = table("chats", column("id"), column("deleted_at"))


class ChatBoundTable(NamedTuple):
    """A table and the column that holds the id of the chat a row belongs to."""

    table: str
    chat_column: str


CHAT_BOUND_TABLES: tuple[ChatBoundTable, ...] = (
    ChatBoundTable("widget_kv", "chat_id"),
    ChatBoundTable("approvals", "chat_id"),
    ChatBoundTable("commitments", "source_chat_id"),
    ChatBoundTable("fission_task_records", "chat_id"),
)


async def delete_trashed_chat_bound_rows(executor: AsyncSession | AsyncConnection, chat_ids: Sequence[str]) -> None:
    """Delete the ``CHAT_BOUND_TABLES`` rows of every chat in ``chat_ids`` that is in the trash.

    The trash check is part of each DELETE, so an id list that went stale (the chat was restored since it was
    read) can never erase a live chat's data. Runs inside the caller's transaction: the rows go together with
    the chat rows or not at all.
    """
    for start in range(0, len(chat_ids), _BATCH_SIZE):
        batch = chat_ids[start : start + _BATCH_SIZE]
        for bound in CHAT_BOUND_TABLES:
            bound_table = table(bound.table, column(bound.chat_column))
            owner = bound_table.c[bound.chat_column]
            in_trash = exists().where(_CHATS.c.id == owner, _CHATS.c.deleted_at.isnot(None))
            await executor.execute(delete(bound_table).where(owner.in_(batch), in_trash))
