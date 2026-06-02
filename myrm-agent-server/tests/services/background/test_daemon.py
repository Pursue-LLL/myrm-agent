"""Test MaintenanceDaemon."""

import asyncio

import pytest

from app.services.background.daemon import MaintenanceDaemon


@pytest.fixture
def daemon():
    d = MaintenanceDaemon()
    yield d
    # Ensure it's stopped after test
    if d._worker_task and not d._worker_task.done():
        d._worker_task.cancel()


@pytest.mark.asyncio
async def test_daemon_starts_and_stops(daemon):
    assert daemon._worker_task is None
    await daemon.start()
    assert daemon._worker_task is not None
    assert not daemon._worker_task.done()

    await daemon.stop(timeout_seconds=0.1)
    assert daemon._worker_task.done()


@pytest.mark.asyncio
async def test_daemon_executes_tasks(daemon):
    await daemon.start()

    flag = False

    async def sample_task():
        nonlocal flag
        flag = True

    daemon.submit(sample_task)

    # Give the worker a chance to process the task
    await asyncio.sleep(0.05)
    assert flag is True


@pytest.mark.asyncio
async def test_daemon_graceful_shutdown_waits_for_queue(daemon):
    await daemon.start()

    task_completed = False

    async def slow_task():
        nonlocal task_completed
        await asyncio.sleep(0.2)
        task_completed = True

    daemon.submit(slow_task)

    # The stop method should block until the queue is empty
    # slow_task takes 0.2s, so stop with 1.0s timeout should succeed
    await daemon.stop(timeout_seconds=1.0)

    assert task_completed is True
    assert daemon._queue.empty()


@pytest.mark.asyncio
async def test_daemon_shutdown_timeout(daemon):
    await daemon.start()

    task_completed = False

    async def extremely_slow_task():
        nonlocal task_completed
        await asyncio.sleep(2.0)
        task_completed = True

    daemon.submit(extremely_slow_task)

    # The stop method with 0.1s timeout should timeout and cancel the worker
    await daemon.stop(timeout_seconds=0.1)

    # Task should not be completed yet because it was cancelled
    assert task_completed is False


@pytest.mark.asyncio
async def test_daemon_bounded_queue_rejects_when_full():
    daemon = MaintenanceDaemon(max_queue_size=2)

    async def noop():
        pass

    # Fill the queue
    daemon.submit(noop)
    daemon.submit(noop)

    # Third submit should raise QueueFull
    with pytest.raises(asyncio.QueueFull):
        daemon.submit(noop)


@pytest.mark.asyncio
async def test_daemon_idempotent_start(daemon):
    """Starting twice should not create a second worker task."""
    await daemon.start()
    task1 = daemon._worker_task
    await daemon.start()
    task2 = daemon._worker_task
    assert task1 is task2

    await daemon.stop(timeout_seconds=0.1)


@pytest.mark.asyncio
async def test_daemon_queue_depth(daemon):
    assert daemon.queue_depth == 0
    await daemon.start()

    event = asyncio.Event()

    async def blocking_task():
        await event.wait()

    daemon.submit(blocking_task)
    daemon.submit(blocking_task)
    assert daemon.queue_depth >= 1

    event.set()
    await asyncio.sleep(0.05)
    await daemon.stop(timeout_seconds=0.5)
