"""The index rows of one memory are replaced as a unit, even when several writers run at once.

One connection serves every coroutine, so an unguarded replacement (delete the old rows, insert the new
ones) interleaves with another and leaves the rows of every writer behind: identifiers the stored text
never held.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from myrm_agent_harness.toolkits.memory.relational.sqlite_store import SQLiteRelationalStore

WRITERS = 24


def index_state(db_path: Path, memory_id: str) -> tuple[list[str], int]:
    """The identifier rows and the full-text document count a memory holds, read from the database file."""
    with sqlite3.connect(db_path) as connection:
        identifiers = [
            row[0]
            for row in connection.execute(
                "SELECT identifier FROM exact_fact_identifiers WHERE memory_id = ?", (memory_id,)
            )
        ]
        documents = connection.execute(
            "SELECT COUNT(*) FROM exact_facts_fts WHERE memory_id = ?", (memory_id,)
        ).fetchone()[0]
    return identifiers, documents


async def record(store: SQLiteRelationalStore, index: int) -> None:
    await store.record_exact_fact(
        memory_id="m1",
        user_id="user",
        content=f"host at 10.0.{index}.1:{1000 + index}",
        identifiers=[f"10.0.{index}.1:{1000 + index}"],
        primary_namespace="ns",
    )


async def test_concurrent_rewrites_of_one_memory_leave_a_single_identifier_set(tmp_path: Path) -> None:
    store = SQLiteRelationalStore(db_path=str(tmp_path / "memory.db"))

    await asyncio.gather(*(record(store, index) for index in range(1, WRITERS + 1)))
    await store.close()

    identifiers, documents = index_state(tmp_path / "memory.db", "m1")
    assert len(identifiers) == 1
    assert documents == 1


async def test_a_delete_racing_rewrites_never_leaves_a_partial_index(tmp_path: Path) -> None:
    store = SQLiteRelationalStore(db_path=str(tmp_path / "memory.db"))

    await asyncio.gather(*(record(store, index) for index in range(1, WRITERS + 1)), store.delete_exact_fact("m1"))
    await store.close()

    identifiers, documents = index_state(tmp_path / "memory.db", "m1")
    assert len(identifiers) in (0, 1)
    assert documents == len(identifiers)
