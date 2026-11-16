"""The goal queue survives unreadable storage and concurrent changes.

A queue that cannot be read is never replaced by an empty one, and the changes of one session all land.
"""

from __future__ import annotations

import asyncio
import errno
import gc
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from myrm_agent_harness.agent.goals import queue_index
from myrm_agent_harness.agent.goals.storage import GoalStorage
from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

_STORAGE_LOGGER = "myrm_agent_harness.agent.goals.storage"
_QUEUE_LOGGER = "myrm_agent_harness.agent.goals.queue_index"
_SESSION = "s-queue"


class _Backend(LocalStorageBackend):
    """A local backend that fails queue reads, or holds one write, on demand."""

    def __init__(self, base_path: Path) -> None:
        super().__init__(base_path)
        self.queue_reads_fail = False
        self.held_key: str | None = None
        self.write_reached = asyncio.Event()
        self.release_write = asyncio.Event()

    async def read(self, key: str) -> bytes:
        if self.queue_reads_fail and key.startswith("goals_queue/"):
            raise OSError(errno.EMFILE, "Too many open files")
        return await super().read(key)

    async def write(self, key: str, content: bytes, content_type: str | None = None) -> None:
        if key == self.held_key:
            self.write_reached.set()
            await self.release_write.wait()
        await super().write(key, content, content_type)


@pytest.fixture
def backend(tmp_path: Path) -> _Backend:
    return _Backend(tmp_path)


@pytest.fixture
def storage(backend: _Backend) -> GoalStorage:
    return GoalStorage(backend)


def _goal(goal_id: str, session_id: str = _SESSION) -> Goal:
    return Goal(goal_id=goal_id, session_id=session_id, objective=goal_id, status=GoalStatus.QUEUED)


def _queue_file(backend: _Backend, session_id: str = _SESSION) -> Path:
    return backend.base_path / "goals_queue" / session_id


async def _queued_ids(storage: GoalStorage, session_id: str = _SESSION) -> list[object]:
    return [entry["goal_id"] for entry in await storage.get_queue(session_id)]


def _records(caplog: pytest.LogCaptureFixture, name: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == name]


_CHANGES: dict[str, Callable[[GoalStorage], Awaitable[None]]] = {
    "add": lambda storage: storage.add_to_queue(_goal("g-new")),
    "remove": lambda storage: storage.remove_from_queue(_SESSION, "g-1"),
    "reorder": lambda storage: storage.reorder_queue(_SESSION, ["g-2", "g-1"]),
}


@pytest.mark.asyncio
async def test_a_missing_queue_is_empty_and_silent(storage: GoalStorage, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        assert await storage.get_queue("never-queued") == []
    assert _records(caplog, _STORAGE_LOGGER) == []
    assert _records(caplog, _QUEUE_LOGGER) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", _CHANGES)
async def test_a_change_to_an_unreadable_queue_raises_and_leaves_it_alone(
    storage: GoalStorage, backend: _Backend, change: str
) -> None:
    await storage.add_to_queue(_goal("g-1"))
    await storage.add_to_queue(_goal("g-2"))
    before = _queue_file(backend).read_bytes()

    backend.queue_reads_fail = True
    with pytest.raises(OSError, match="Too many open files"):
        await _CHANGES[change](storage)
    backend.queue_reads_fail = False

    assert _queue_file(backend).read_bytes() == before
    assert await _queued_ids(storage) == ["g-1", "g-2"]


@pytest.mark.asyncio
async def test_a_plain_read_of_an_unreadable_queue_is_empty_and_names_the_session(
    storage: GoalStorage, backend: _Backend, caplog: pytest.LogCaptureFixture
) -> None:
    await storage.add_to_queue(_goal("g-1"))

    backend.queue_reads_fail = True
    with caplog.at_level(logging.WARNING, logger=_STORAGE_LOGGER):
        assert await storage.get_queue(_SESSION) == []
    [record] = _records(caplog, _STORAGE_LOGGER)

    assert record.levelno == logging.WARNING
    assert f"Goal queue index for session '{_SESSION}'" in record.getMessage()


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"\xff\xfe", b"{not json", b'{"goal_id": "g-1"}', b"null"])
async def test_a_queue_that_is_not_a_json_list_is_logged_and_repaired_by_the_next_write(
    storage: GoalStorage, backend: _Backend, caplog: pytest.LogCaptureFixture, content: bytes
) -> None:
    _queue_file(backend).parent.mkdir(parents=True)
    _queue_file(backend).write_bytes(content)

    with caplog.at_level(logging.ERROR, logger=_QUEUE_LOGGER):
        assert await storage.get_queue(_SESSION) == []
    [record] = _records(caplog, _QUEUE_LOGGER)
    assert record.levelno == logging.ERROR
    assert f"session '{_SESSION}'" in record.getMessage()

    await storage.add_to_queue(_goal("g-1"))
    assert await _queued_ids(storage) == ["g-1"]


@pytest.mark.asyncio
async def test_concurrent_adds_to_one_session_all_land(storage: GoalStorage) -> None:
    goals = [_goal(f"g-{i}") for i in range(20)]

    await asyncio.gather(*(storage.add_to_queue(goal) for goal in goals))

    assert sorted(await _queued_ids(storage)) == sorted(goal.goal_id for goal in goals)


@pytest.mark.asyncio
async def test_concurrent_removes_from_one_session_all_land(storage: GoalStorage) -> None:
    goals = [_goal(f"g-{i}") for i in range(20)]
    for goal in goals:
        await storage.add_to_queue(goal)

    await asyncio.gather(*(storage.remove_from_queue(_SESSION, goal.goal_id) for goal in goals))

    assert await _queued_ids(storage) == []


@pytest.mark.asyncio
async def test_a_session_does_not_wait_for_another_sessions_change(storage: GoalStorage, backend: _Backend) -> None:
    backend.held_key = "goals_queue/s-slow"
    slow = asyncio.create_task(storage.add_to_queue(_goal("g-slow", "s-slow")))
    try:
        await asyncio.wait_for(backend.write_reached.wait(), timeout=5)
        await asyncio.wait_for(storage.add_to_queue(_goal("g-fast", "s-fast")), timeout=5)
        assert not slow.done()
    finally:
        backend.release_write.set()  # a failed assertion must not leave the held lock to the next test
        await slow

    assert await _queued_ids(storage, "s-slow") == ["g-slow"]
    assert await _queued_ids(storage, "s-fast") == ["g-fast"]


@pytest.mark.asyncio
async def test_a_sessions_lock_is_dropped_once_its_changes_are_done(storage: GoalStorage) -> None:
    sessions = [f"s-{i}" for i in range(50)]
    await asyncio.gather(*(storage.add_to_queue(_goal("g-1", session)) for session in sessions))
    gc.collect()

    assert not any(session in queue_index._SESSION_LOCKS for session in sessions)
