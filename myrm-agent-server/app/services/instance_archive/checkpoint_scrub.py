"""The conversation checkpoints of web incognito chats, removed from every archived copy of checkpoints.db.

[INPUT]
- myrm_agent_harness.runtime.context.session.session_continuity::resolve_thread_ids (POS: the thread aliases the runtime gives a chat)
- app.services.instance_archive.table_policy::live_web_incognito_chat_ids (POS: which chats are web incognito)

[OUTPUT]
- CHECKPOINTS_DB_NAME: file name of the LangGraph checkpoint database in the state directory
- scrub_checkpoint_threads: delete the threads of the given chats from a detached copy
- live_checkpoint_scrubber: the ``prepare`` callback the export applies to its checkpoints.db copy

[POS]
A checkpoint holds the whole channel state of a turn, message text and tool results included, and the runtime
writes one for incognito chats too. The incognito scrub of data.db therefore does not cover it: the same chats
have to leave this file, or the archive still carries what the chat rows no longer name. Threads are keyed by chat
id with no foreign key, so every table with a ``thread_id`` column is cleared (a table the checkpointer adds later
is covered without a change here).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path

from myrm_agent_harness.runtime.context.session.session_continuity import resolve_thread_ids

from app.services.instance_archive.table_policy import column_names, live_web_incognito_chat_ids, table_names

CHECKPOINTS_DB_NAME = "checkpoints.db"

# Thread ids per DELETE: far below SQLite's bound-parameter limit on any build.
_BATCH_SIZE = 400


def scrub_checkpoint_threads(db_path: Path, chat_ids: Sequence[str]) -> None:
    """Delete every checkpoint thread of ``chat_ids`` from the detached checkpoint database at ``db_path``."""
    thread_ids = [thread_id for chat_id in chat_ids for thread_id in resolve_thread_ids(chat_id)]
    if not thread_ids:
        return
    conn = sqlite3.connect(db_path)
    try:
        # Freed pages are zeroed, otherwise the deleted message text stays readable in the file.
        conn.execute("PRAGMA secure_delete = ON")
        for table in sorted(table_names(conn)):
            if "thread_id" not in column_names(conn, table):
                continue
            for start in range(0, len(thread_ids), _BATCH_SIZE):
                batch = thread_ids[start : start + _BATCH_SIZE]
                placeholders = ", ".join("?" * len(batch))
                conn.execute(f'DELETE FROM "{table}" WHERE thread_id IN ({placeholders})', batch)
        conn.commit()
    finally:
        conn.close()


def live_checkpoint_scrubber(main_db: Path) -> Callable[[Path], None]:
    """``prepare`` callback for the checkpoints.db copy of an export.

    The chats are read from the live ``main_db`` when the copy is made, not from data.db's own snapshot taken at
    another moment: a chat that started in between has a thread in the copy and no row in that snapshot. A failure
    here makes the archive writer leave the checkpoints out and report them, never carry them unscrubbed.
    """

    def scrub(copy: Path) -> None:
        scrub_checkpoint_threads(copy, live_web_incognito_chat_ids(main_db))

    return scrub
