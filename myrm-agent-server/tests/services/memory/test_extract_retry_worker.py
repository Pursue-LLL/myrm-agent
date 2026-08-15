"""Tests for the memory extraction retry worker sweep."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.services.memory.extract_retry.extract_retry_worker import (
    ExtractRetryWorker,
    _record_terminal_failure,
)


@asynccontextmanager
async def _fake_db_session() -> AsyncIterator[None]:
    yield None


@pytest.mark.asyncio
async def test_sweep_deletes_row_on_success() -> None:
    worker = ExtractRetryWorker()
    with (
        patch(
            "app.services.memory.extract_retry.extract_retry_queue.claim_due",
            AsyncMock(return_value=[("chat-1", 1)]),
        ),
        patch(
            "app.services.memory.extract_retry.retry_chat_memory_extract.run_retry_extract_for_chat",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.services.memory.extract_retry.extract_retry_queue.delete",
            AsyncMock(),
        ) as mock_delete,
        patch(
            "app.services.memory.extract_retry.extract_retry_queue.mark_failure",
            AsyncMock(),
        ) as mock_mark_failure,
    ):
        await worker._sweep()

    mock_delete.assert_awaited_once_with("chat-1")
    mock_mark_failure.assert_not_awaited()
    assert worker._running == set()


@pytest.mark.asyncio
async def test_sweep_schedules_backoff_on_failure() -> None:
    worker = ExtractRetryWorker()
    with (
        patch(
            "app.services.memory.extract_retry.extract_retry_queue.claim_due",
            AsyncMock(return_value=[("chat-1", 1)]),
        ),
        patch(
            "app.services.memory.extract_retry.retry_chat_memory_extract.run_retry_extract_for_chat",
            AsyncMock(side_effect=TimeoutError("llm timeout")),
        ),
        patch(
            "app.services.memory.extract_retry.extract_retry_queue.delete",
            AsyncMock(),
        ) as mock_delete,
        patch(
            "app.services.memory.extract_retry.extract_retry_queue.mark_failure",
            AsyncMock(return_value=False),
        ) as mock_mark_failure,
        patch(
            "app.services.memory.extract_retry.extract_retry_worker._record_terminal_failure",
            AsyncMock(),
        ) as mock_terminal,
    ):
        await worker._sweep()

    mock_mark_failure.assert_awaited_once()
    args = mock_mark_failure.await_args.args
    assert args[0] == "chat-1"
    assert args[1] == 1
    assert "llm timeout" in args[2]
    mock_delete.assert_not_awaited()
    mock_terminal.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweep_records_terminal_failure_when_attempts_exhausted() -> None:
    worker = ExtractRetryWorker()
    with (
        patch(
            "app.services.memory.extract_retry.extract_retry_queue.claim_due",
            AsyncMock(return_value=[("chat-1", 3)]),
        ),
        patch(
            "app.services.memory.extract_retry.retry_chat_memory_extract.run_retry_extract_for_chat",
            AsyncMock(side_effect=RuntimeError("permanent")),
        ),
        patch(
            "app.services.memory.extract_retry.extract_retry_queue.mark_failure",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.services.memory.extract_retry.extract_retry_worker._record_terminal_failure",
            AsyncMock(),
        ) as mock_terminal,
    ):
        await worker._sweep()

    mock_terminal.assert_awaited_once()
    args = mock_terminal.await_args.args
    assert args[0] == "chat-1"
    assert args[1] == 3
    assert isinstance(args[2], RuntimeError)


@pytest.mark.asyncio
async def test_wake_triggers_immediate_sweep() -> None:
    worker = ExtractRetryWorker()
    sweeps = asyncio.Event()
    sweep_count = {"n": 0}

    async def fake_sweep() -> None:
        sweep_count["n"] += 1
        sweeps.set()

    worker._sweep = fake_sweep  # type: ignore[method-assign]
    await worker.start()
    await asyncio.wait_for(sweeps.wait(), timeout=2)
    assert sweep_count["n"] == 1

    sweeps.clear()
    worker.wake()
    await asyncio.wait_for(sweeps.wait(), timeout=2)
    assert sweep_count["n"] == 2
    await worker.stop()


@pytest.mark.asyncio
async def test_wake_during_sweep_triggers_immediate_rescan() -> None:
    """A wake() arriving while a sweep runs must not be swallowed by the loop."""
    worker = ExtractRetryWorker()
    sweep_count = {"n": 0}
    second_sweep_done = asyncio.Event()

    async def fake_sweep() -> None:
        sweep_count["n"] += 1
        if sweep_count["n"] == 1:
            worker.wake()
        if sweep_count["n"] == 2:
            second_sweep_done.set()

    worker._sweep = fake_sweep  # type: ignore[method-assign]
    await worker.start()
    # A swallowed wake would leave the loop idle for SWEEP_INTERVAL_SECONDS (60s),
    # so a 2s timeout proves the in-sweep wake triggered an immediate re-sweep.
    await asyncio.wait_for(second_sweep_done.wait(), timeout=2)
    assert sweep_count["n"] == 2
    await worker.stop()


@pytest.mark.asyncio
async def test_start_is_idempotent() -> None:
    worker = ExtractRetryWorker()
    await worker.start()
    first_task = worker._task
    await worker.start()
    assert worker._task is first_task
    await worker.stop()
    assert worker._task is None


@pytest.mark.asyncio
async def test_stop_without_start_is_noop() -> None:
    worker = ExtractRetryWorker()
    await worker.stop()
    assert worker._task is None


@pytest.mark.asyncio
async def test_sweep_claim_failure_is_handled() -> None:
    worker = ExtractRetryWorker()
    with patch(
        "app.services.memory.extract_retry.extract_retry_queue.claim_due",
        AsyncMock(side_effect=RuntimeError("db down")),
    ):
        await worker._sweep()
    assert worker._running == set()


@pytest.mark.asyncio
async def test_sweep_cleanup_failure_keeps_loop_alive() -> None:
    """delete failure must be contained: running set is still released."""
    worker = ExtractRetryWorker()
    with (
        patch(
            "app.services.memory.extract_retry.extract_retry_queue.claim_due",
            AsyncMock(return_value=[("chat-1", 1)]),
        ),
        patch(
            "app.services.memory.extract_retry.retry_chat_memory_extract.run_retry_extract_for_chat",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.services.memory.extract_retry.extract_retry_queue.delete",
            AsyncMock(side_effect=RuntimeError("db down")),
        ),
    ):
        await worker._sweep()
    assert worker._running == set()


@pytest.mark.asyncio
async def test_loop_continues_after_sweep_exception() -> None:
    """A sweep exception is logged and the loop keeps running."""
    worker = ExtractRetryWorker()
    second_sweep_done = asyncio.Event()
    sweep_count = {"n": 0}

    async def fake_sweep() -> None:
        sweep_count["n"] += 1
        if sweep_count["n"] == 1:
            raise RuntimeError("boom")
        second_sweep_done.set()

    worker._sweep = fake_sweep  # type: ignore[method-assign]
    await worker.start()
    await asyncio.sleep(0.05)  # let the failing sweep finish and the loop go idle
    assert sweep_count["n"] == 1
    worker.wake()
    await asyncio.wait_for(second_sweep_done.wait(), timeout=2)
    assert sweep_count["n"] == 2
    await worker.stop()


@pytest.mark.asyncio
async def test_loop_survives_wait_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wait timeout merely schedules the next sweep; the loop never dies."""
    import app.services.memory.extract_retry.extract_retry_worker as extract_retry_worker

    monkeypatch.setattr(extract_retry_worker, "SWEEP_INTERVAL_SECONDS", 0.05)
    worker = ExtractRetryWorker()
    second_sweep_done = asyncio.Event()
    sweep_count = {"n": 0}

    async def fake_sweep() -> None:
        sweep_count["n"] += 1
        if sweep_count["n"] == 2:
            second_sweep_done.set()

    worker._sweep = fake_sweep  # type: ignore[method-assign]
    await worker.start()
    await asyncio.wait_for(second_sweep_done.wait(), timeout=2)
    assert sweep_count["n"] == 2
    await worker.stop()


@pytest.mark.asyncio
async def test_loop_cancelled_during_sweep_propagates() -> None:
    worker = ExtractRetryWorker()

    async def fake_sweep() -> None:
        await asyncio.sleep(10)

    worker._sweep = fake_sweep  # type: ignore[method-assign]
    await worker.start()
    await asyncio.sleep(0.05)  # enter the long-running sweep
    await worker.stop()
    assert worker._task is None


@pytest.mark.asyncio
async def test_record_terminal_failure_writes_ledger() -> None:
    with (
        patch(
            "app.database.connection.get_session",
            _fake_db_session,
        ),
        patch(
            "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
        ) as mock_cls,
    ):
        mock_cls.return_value.record_event = AsyncMock()
        await _record_terminal_failure("chat-1", 3, RuntimeError("boom"))

    mock_cls.return_value.record_event.assert_awaited_once()
    kwargs = mock_cls.return_value.record_event.await_args.kwargs
    assert kwargs["source"] == "memory_extract_retry_worker"
    assert kwargs["metadata"]["attempts"] == 3
    assert kwargs["metadata"]["error"].endswith("RuntimeError: boom")


@pytest.mark.asyncio
async def test_record_terminal_failure_survives_ledger_error() -> None:
    with (
        patch(
            "app.database.connection.get_session",
            _fake_db_session,
        ),
        patch(
            "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
        ) as mock_cls,
    ):
        mock_cls.return_value.record_event = AsyncMock(
            side_effect=RuntimeError("ledger down")
        )
        await _record_terminal_failure("chat-1", 3, RuntimeError("boom"))
    # Must not raise: a broken ledger must never crash the worker.
