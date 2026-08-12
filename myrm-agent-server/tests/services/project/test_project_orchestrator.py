"""Tests for ProjectOrchestrator per-project async locking."""

from __future__ import annotations

import asyncio

from app.services.project.orchestrator import ProjectOrchestrator


def test_get_lock_creates_on_first_access() -> None:
    orch = ProjectOrchestrator()
    lock = orch.get_lock("proj-1")
    assert lock is orch.get_lock("proj-1")
    assert lock.locked() is False


def test_is_locked_is_pure_query_without_creation() -> None:
    orch = ProjectOrchestrator()
    assert orch.is_locked("never-touched") is False
    assert len(orch._locks) == 0


async def test_acquire_release_roundtrip() -> None:
    orch = ProjectOrchestrator()
    await orch.acquire("proj-1")
    assert orch.is_locked("proj-1") is True
    orch.release("proj-1")
    assert orch.is_locked("proj-1") is False


async def test_release_clears_idle_lock() -> None:
    orch = ProjectOrchestrator()
    await orch.acquire("proj-1")
    assert len(orch._locks) == 1
    orch.release("proj-1")
    assert len(orch._locks) == 0
    assert orch.is_locked("proj-1") is False


async def test_release_with_waiter_keeps_lock() -> None:
    orch = ProjectOrchestrator()
    await orch.acquire("proj-1")

    acquired_holder: list[bool] = []

    async def contender() -> None:
        await orch.acquire("proj-1")
        acquired_holder.append(True)
        orch.release("proj-1")

    task = asyncio.create_task(contender())
    await asyncio.sleep(0.01)
    assert task.done() is False

    orch.release("proj-1")
    await asyncio.wait_for(task, timeout=2)
    assert acquired_holder == [True]
    # 锁有等待者期间保留，等待者接手后释放
    assert len(orch._locks) == 0


async def test_forget_removes_idle_lock() -> None:
    orch = ProjectOrchestrator()
    await orch.acquire("proj-1")
    orch.release("proj-1")
    orch.forget("proj-1")
    assert len(orch._locks) == 0
    assert orch.is_locked("proj-1") is False


async def test_forget_skips_held_lock() -> None:
    orch = ProjectOrchestrator()
    await orch.acquire("proj-1")
    orch.forget("proj-1")
    assert len(orch._locks) == 1
    orch.release("proj-1")
    assert len(orch._locks) == 0


async def test_forget_unknown_project_is_noop() -> None:
    orch = ProjectOrchestrator()
    orch.forget("ghost")
    assert len(orch._locks) == 0


async def test_cancelled_waiter_does_not_break_next_contender() -> None:
    """Cancelled lock waiter must not corrupt the lock for subsequent contenders.

    Real scenario: a user cancels their request while another agent holds the
    project lock. asyncio.Lock removes the cancelled waiter from _waiters, and
    the lock must remain usable by the next real contender.
    """
    orch = ProjectOrchestrator()
    await orch.acquire("proj-1")

    cancelled: list[bool] = []

    async def waiter() -> None:
        try:
            await orch.acquire("proj-1")
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0.01)
    assert task.done() is False, "waiter should be blocked on the held lock"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled == [True]

    # Holder still owns the lock; the cancelled waiter must not have released it.
    assert orch.is_locked("proj-1") is True

    # A fresh contender can still acquire the lock normally after release.
    acquired: list[bool] = []

    async def contender() -> None:
        await orch.acquire("proj-1")
        acquired.append(True)
        orch.release("proj-1")

    await asyncio.wait_for(contender(), timeout=2)
    assert acquired == [True]
    assert orch.is_locked("proj-1") is False


async def test_parallel_contenders_serialize_on_same_project() -> None:
    orch = ProjectOrchestrator()
    order: list[int] = []

    async def worker(tag: int) -> None:
        await orch.acquire("shared")
        order.append(tag)
        await asyncio.sleep(0.01)
        orch.release("shared")

    await asyncio.gather(worker(1), worker(2), worker(3))
    assert order == [1, 2, 3]


async def test_different_projects_do_not_block_each_other() -> None:
    orch = ProjectOrchestrator()
    order: list[str] = []

    async def worker(project: str, tag: str) -> None:
        await orch.acquire(project)
        order.append(tag)
        await asyncio.sleep(0.01)
        orch.release(project)

    await asyncio.gather(worker("p-a", "a"), worker("p-b", "b"))
    assert set(order) == {"a", "b"}
