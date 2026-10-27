"""An inventory page must not lose its write to a writer that commits between its read and its write.

``upsert_inventory`` reads the page's existing ledger rows, then inserts or updates them. Under the deferred-read
transaction policy another writer committing in between aborts the unit with SQLITE_BUSY_SNAPSHOT, which ``busy_timeout``
does not cover; the slice then fails with an internal error and waits out a growing backoff. The test runs the real
transaction policy on a file database.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from app.services.wiki.source_sync.ima import inventory
from app.services.wiki.source_sync.ima.ledger import InventoryItem
from app.services.wiki.source_sync.ima.state import ImaSyncState
from tests.support.policy_sqlite import BUSY_TIMEOUT_MS, READ_GRACE_S, PolicyDb, hold_write_lock, policy_database, wait_until

from .support import FakeIma, library_config, make_ctx, rows


@pytest_asyncio.fixture
async def policy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[PolicyDb]:
    async with policy_database(tmp_path / "ima.db", monkeypatch) as db:
        yield db


@pytest.mark.asyncio
async def test_inventory_page_keeps_its_write_when_another_writer_commits_first(policy_db: PolicyDb, tmp_path: Path) -> None:
    ctx = make_ctx(FakeIma(), tmp_path, config=library_config(), state=ImaSyncState())
    ctx.state.generation = 1
    item = InventoryItem(
        item_key="kb1:doc1",
        container_id="kb1",
        container_name="Library",
        remote_id="doc1",
        title="Plan",
        folder_path="",
        media_type=7,
        remote_version="1",
    )

    holder = await hold_write_lock(policy_db)
    try:
        record = asyncio.create_task(inventory._record(ctx, [item]))
        # Unprotected, the page reads its existing rows within milliseconds and keeps that snapshot; protected, it waits
        # for the lock first and issues no read until the holder is done.
        await wait_until(policy_db.read_issued, READ_GRACE_S)
        await holder.commit()

        await asyncio.wait_for(record, timeout=BUSY_TIMEOUT_MS / 1000)
    finally:
        await holder.close()

    assert set(await rows(policy_db.factory)) == {"Plan"}
