"""Unit tests for background registry stdout/stderr consume loop."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.consume import (
    BackgroundRegistryEntry,
    consume_background_entry,
)
from myrm_agent_harness.agent.meta_tools.bash._background.types import BackgroundProcessInfo
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.fake_background_proc import FakeOutputPipe, FakeProc, wait_until


class _FailingPipe:
    """A pipe whose read fails, as one does when the other end vanishes."""

    async def read(self, n: int = -1) -> bytes:
        raise OSError("pipe closed")


def _make_entry(
    proc: FakeProc,
    *,
    finish_listener: AsyncMock | None = None,
    progress_listener: AsyncMock | None = None,
    spill_writer: MagicMock | None = None,
) -> BackgroundRegistryEntry:
    info = BackgroundProcessInfo(
        job_id="a" * 32,
        pid=proc.pid,
        command="echo test",
        session_id="sess-consume",
        started_at=1.0,
        status="running",
    )
    return BackgroundRegistryEntry(
        info=info,
        proc=cast(AsyncProcessProtocol, proc),
        stdout_buffer=deque(maxlen=200),
        stderr_buffer=deque(maxlen=200),
        finish_listener=finish_listener,
        progress_listener=progress_listener,
        spill_writer=spill_writer,
    )


async def _run_consume(entry: BackgroundRegistryEntry) -> list[int]:
    reaped: list[int] = []

    await consume_background_entry(
        entry,
        snapshot=lambda e: e.info,
        schedule_reap=lambda pid: reaped.append(pid),
    )
    return reaped


@pytest.mark.asyncio
async def test_consume_background_entry_captures_stdout_and_exits() -> None:
    proc = FakeProc(pid=4242, stdout=[b"hello\n"], stderr=[])
    entry = _make_entry(proc)

    task = asyncio.create_task(_run_consume(entry))
    await asyncio.sleep(0.05)
    proc.finish(exit_code=0)
    reaped = await task

    assert entry.info.status == "exited"
    assert entry.info.exit_code == 0
    assert list(entry.stdout_buffer) == ["hello"]
    assert reaped == [4242]


@pytest.mark.asyncio
async def test_consume_background_entry_invokes_finish_listener() -> None:
    proc = FakeProc(pid=7777, stdout=[b"done\n"], stderr=[])
    listener = AsyncMock()
    entry = _make_entry(proc, finish_listener=listener)

    task = asyncio.create_task(_run_consume(entry))
    await asyncio.sleep(0.05)
    proc.finish(exit_code=0)
    await task

    listener.assert_awaited_once()


@pytest.mark.asyncio
async def test_consume_background_entry_persists_terminal_state() -> None:
    proc = FakeProc(pid=8888, stdout=[b"line\n"], stderr=[])
    entry = _make_entry(proc)

    with patch(
        "myrm_agent_harness.agent.meta_tools.bash._background.store_sync.persist_terminal_state",
    ) as persist:
        task = asyncio.create_task(_run_consume(entry))
        await asyncio.sleep(0.05)
        proc.finish(exit_code=0)
        await task

    persist.assert_called_once_with(entry.info)


@pytest.mark.asyncio
async def test_consume_background_entry_captures_stderr() -> None:
    proc = FakeProc(pid=1111, stdout=[], stderr=[b"warn\n"])
    entry = _make_entry(proc)

    task = asyncio.create_task(_run_consume(entry))
    await asyncio.sleep(0.05)
    proc.finish(exit_code=1)
    await task

    assert list(entry.stderr_buffer) == ["warn"]
    assert entry.info.exit_code == 1


@pytest.mark.asyncio
async def test_consume_background_entry_truncates_long_lines() -> None:
    long_payload = b"x" * 33_000 + b"\n"
    proc = FakeProc(pid=2222, stdout=[long_payload], stderr=[])
    entry = _make_entry(proc)

    task = asyncio.create_task(_run_consume(entry))
    await asyncio.sleep(0.05)
    proc.finish()
    await task

    captured = entry.stdout_buffer[0]
    assert captured.endswith("... [+232 chars truncated]")
    assert len(captured) <= 32 * 1024 + 64


@pytest.mark.asyncio
async def test_consume_background_entry_emits_progress() -> None:
    progress_line = b'MYRM_PROGRESS {"percent": 50, "message": "Building"}\n'
    proc = FakeProc(pid=3333, stdout=[progress_line], stderr=[])
    progress_listener = AsyncMock()
    entry = _make_entry(proc, progress_listener=progress_listener)

    task = asyncio.create_task(_run_consume(entry))
    await asyncio.sleep(0.05)
    proc.finish()
    await task

    progress_listener.assert_awaited_once()
    assert entry.info.last_progress is not None
    assert entry.info.last_progress.get("progress") == 50


@pytest.mark.asyncio
async def test_consume_background_entry_spill_writer_persists_vault_ref() -> None:
    spill = MagicMock()
    spill.vault_log_ref = "output_spill.txt"
    proc = FakeProc(pid=4444, stdout=[b"spilled\n"], stderr=[])
    entry = _make_entry(proc, spill_writer=spill)

    with patch(
        "myrm_agent_harness.agent.meta_tools.bash._background.store_sync.persist_vault_log_ref",
    ) as persist_ref:
        task = asyncio.create_task(_run_consume(entry))
        await asyncio.sleep(0.05)
        proc.finish()
        await task

    spill.append_line.assert_called_once_with("stdout", "spilled")
    persist_ref.assert_called_once_with(entry.info)
    assert entry.info.vault_log_ref == "output_spill.txt"


@pytest.mark.asyncio
async def test_a_pipe_whose_read_fails_ends_that_stream_only() -> None:
    proc = FakeProc(pid=5555, stdout=[], stderr=[b"warn\n"], stdout_pipe=_FailingPipe())
    entry = _make_entry(proc)

    task = asyncio.create_task(_run_consume(entry))
    await asyncio.sleep(0.05)
    proc.finish()
    await task

    assert list(entry.stdout_buffer) == []
    assert list(entry.stderr_buffer) == ["warn"]
    assert entry.info.status == "exited"


@pytest.mark.asyncio
async def test_consume_background_entry_skips_stream_without_read() -> None:
    proc = FakeProc(pid=6666, stdout=[], stderr=[], stdout_pipe=object(), stderr_pipe=object())
    entry = _make_entry(proc)

    task = asyncio.create_task(_run_consume(entry))
    await asyncio.sleep(0.05)
    proc.finish()
    await task

    assert entry.stdout_buffer == deque()
    assert entry.info.status == "exited"


@pytest.mark.asyncio
async def test_what_a_job_prints_without_a_newline_stays_visible_until_it_is_answered() -> None:
    pipe = FakeOutputPipe([b"Continue? [y/N] "], hold_open=True)
    proc = FakeProc(pid=6001, stdout=[], stdout_pipe=pipe)
    entry = _make_entry(proc)

    task = asyncio.create_task(_run_consume(entry))
    await wait_until(lambda: entry.stdout_unfinished.text != "", what="the prompt to reach the unfinished tail")

    assert entry.stdout_unfinished.text == "Continue? [y/N] "
    assert list(entry.stdout_buffer) == []
    assert entry.info.last_output_at == entry.stdout_unfinished.at

    pipe.feed(b"y\n")
    await wait_until(lambda: bool(entry.stdout_buffer), what="the answered line to complete")
    assert list(entry.stdout_buffer) == ["Continue? [y/N] y"]
    assert entry.stdout_unfinished.text == ""

    pipe.close()
    proc.finish()
    await task


@pytest.mark.asyncio
async def test_output_without_a_newline_counts_as_output() -> None:
    """A progress bar redraws one line with carriage returns and never completes a line."""
    pipe = FakeOutputPipe([b"10%\r"], hold_open=True)
    proc = FakeProc(pid=6002, stdout=[], stdout_pipe=pipe)
    entry = _make_entry(proc)
    entry.info.last_output_at = 1.0

    task = asyncio.create_task(_run_consume(entry))
    await wait_until(lambda: entry.info.last_output_at > 1.0, what="the bytes to move last_output_at")

    pipe.close()
    proc.finish()
    await task
    assert list(entry.stdout_buffer) == ["10%"]


@pytest.mark.asyncio
async def test_the_unfinished_line_becomes_the_last_line_when_the_stream_ends() -> None:
    proc = FakeProc(pid=6003, stdout=[b"done\nfinal"], stderr=[])
    entry = _make_entry(proc)

    task = asyncio.create_task(_run_consume(entry))
    await asyncio.sleep(0.05)
    proc.finish()
    await task

    assert list(entry.stdout_buffer) == ["done", "final"]
    assert entry.stdout_unfinished.text == ""


@pytest.mark.asyncio
async def test_consume_background_entry_cancelled_returns_without_crash() -> None:
    proc = FakeProc(pid=9999, stdout=[b"block\n"], stderr=[])
    entry = _make_entry(proc)
    reaped: list[int] = []

    task = asyncio.create_task(
        consume_background_entry(
            entry,
            snapshot=lambda e: e.info,
            schedule_reap=lambda pid: reaped.append(pid),
        )
    )
    await asyncio.sleep(0.02)
    task.cancel()
    await task

    assert reaped == [9999]
