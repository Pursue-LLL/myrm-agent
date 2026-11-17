"""IdleTaskRegistry persistence semantics and the aiosqlite-unavailable guards."""

import asyncio
import sqlite3
from pathlib import Path

import aiosqlite
import pytest

from myrm_agent_harness.agent.background_worker import registry as registry_module
from myrm_agent_harness.agent.background_worker.registry import IdleTaskRegistry


@pytest.fixture
def registry(tmp_path: Path) -> IdleTaskRegistry:
    return IdleTaskRegistry(str(tmp_path / "idle.db"))


@pytest.mark.asyncio
async def test_enqueue_deduplicates_a_task_type_that_is_already_pending(registry: IdleTaskRegistry) -> None:
    await registry.enqueue("s1", "cognitive_consolidation", {})
    await registry.enqueue("s1", "cognitive_consolidation", {})

    first = await registry.acquire_next("s1")

    assert first is not None
    assert first.payload == {}
    assert await registry.acquire_next("s1") is None


@pytest.mark.asyncio
async def test_payload_round_trips_as_json_object(registry: IdleTaskRegistry) -> None:
    await registry.enqueue("s1", "context_compaction", {"chat_id": "c1"})

    record = await registry.acquire_next("s1")

    assert record is not None
    assert record.payload == {"chat_id": "c1"}


@pytest.mark.asyncio
async def test_every_operation_is_a_noop_when_aiosqlite_is_unavailable(
    registry: IdleTaskRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry_module, "aiosqlite", None)

    await registry.init_db()
    await registry.enqueue("s1", "cognitive_consolidation", {})
    assert await registry.acquire_next("s1") is None
    assert await registry.has_pending("s1") is False
    await registry.requeue(1)
    await registry.mark_completed(1)
    await registry.mark_error(1)
    assert await registry.cleanup_old_tasks() == 0


@pytest.mark.asyncio
async def test_has_pending_sees_the_session_and_global_queues_only_while_rows_are_pending(
    registry: IdleTaskRegistry,
) -> None:
    assert await registry.has_pending("s1") is False

    await registry.enqueue("other", "cognitive_consolidation", {})
    assert await registry.has_pending("s1") is False

    await registry.enqueue("global", "cognitive_subsumption", {"new_knowledge": "k"})
    assert await registry.has_pending("s1") is True

    task = await registry.acquire_next("s1")
    assert task is not None
    assert await registry.has_pending("s1") is False  # running rows are not pending

    await registry.requeue(task.id)
    assert await registry.has_pending("s1") is True


@pytest.mark.asyncio
async def test_a_claim_cancelled_before_its_row_is_fetched_leaves_no_write_lock(
    registry: IdleTaskRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    await registry.enqueue("s1", "cognitive_consolidation", {})
    claim_fetch_started = asyncio.Event()
    real_fetchone = aiosqlite.Cursor.fetchone

    async def fetchone_that_waits_to_be_cancelled(cursor: aiosqlite.Cursor) -> sqlite3.Row | None:
        # Only the claim's ``RETURNING *`` row: opening the connection fetches the journal-mode PRAGMA row the same way.
        if cursor.description and cursor.description[0][0] == "id":
            claim_fetch_started.set()
            await asyncio.Event().wait()
        return await real_fetchone(cursor)

    monkeypatch.setattr(aiosqlite.Cursor, "fetchone", fetchone_that_waits_to_be_cancelled)

    claim = asyncio.create_task(registry.acquire_next("s1"))
    async with asyncio.timeout(10):
        await claim_fetch_started.wait()
    claim.cancel()
    with pytest.raises(asyncio.CancelledError) as cancelled:
        await claim

    # ``cancelled`` still references the abandoned claim's frames and so its cursor, as the frames of a cancelled task
    # do until the garbage collector runs: the idle queue's write lock must be gone while that cursor is alive.
    other = sqlite3.connect(registry.db_path, timeout=0)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.rollback()
    finally:
        other.close()
    assert cancelled.value.__traceback__ is not None


def test_registry_is_shared_per_process_and_a_different_root_is_rejected_loudly(
    tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(registry_module, "_registry_instance", None)

    first = registry_module.get_idle_task_registry(str(tmp_path / "a"))
    assert registry_module.get_idle_task_registry(str(tmp_path / "a")) is first
    assert "ignoring request" not in caplog.text

    with caplog.at_level("WARNING", logger=registry_module.logger.name):
        other = registry_module.get_idle_task_registry(str(tmp_path / "b"))

    assert other is first
    assert first.db_path == str(tmp_path / "a" / ".context" / "system" / "idle_tasks.db")
    assert "ignoring request" in caplog.text
