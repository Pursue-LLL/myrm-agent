"""AcpRuntime sends a turn's images as image blocks to an agent that advertises them; a stalled agent cannot hold up a stop."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import signal
import sys
import time
from asyncio.subprocess import Process
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime import stalled_agent
from myrm_agent_harness.toolkits.acp.runtime.acp_runtime import AcpRuntime
from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import IMAGES_NOT_SENT_STATUS, RuntimeConfig, RuntimeEvent, RuntimeEventType

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stalled agent is ended with a POSIX signal")

_AGENTS = Path(__file__).parents[1]
_MOCK_AGENT = _AGENTS / "_mock_acp_agent.py"
_STALLED_AGENT = _AGENTS / "_stalled_acp_agent.py"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Far longer than any wait below: an agent still asleep proves the stop did not wait for it.
_STALL_SECONDS = "60"


def _png(directory: Path, name: str, size: int) -> tuple[Path, bytes]:
    body = _PNG_SIGNATURE + bytes(range(256)) * ((size - len(_PNG_SIGNATURE)) // 256)
    path = directory / name
    path.write_bytes(body)
    return path, body


def _digest(body: bytes) -> str:
    """What the mock agent reports for an image block that carries ``body``."""
    data = base64.b64encode(body).decode("ascii")
    return f"image/png:{len(data)}:{hashlib.sha256(data.encode()).hexdigest()[:16]}"


def _pool(cwd: Path, *agent_args: str) -> RuntimePool:
    pool = RuntimePool(max_concurrent=1)
    pool.register(
        "mock",
        RuntimeConfig(
            backend_type="acp",
            command=sys.executable,
            args=[str(_MOCK_AGENT), *agent_args],
            cwd=str(cwd),
            timeout_seconds=60,
        ),
    )
    return pool


async def _turn(pool: RuntimePool, images: list[str]) -> tuple[str, list[RuntimeEvent]]:
    text: list[str] = []
    events: list[RuntimeEvent] = []
    async for event in pool.run_turn("mock", "look at this", session_id="chat-1", images=images):
        events.append(event)
        if event.type == RuntimeEventType.TEXT_DELTA:
            text.append(str(event.data.get("content")))
    return "".join(text), events


def _not_sent_notices(events: list[RuntimeEvent]) -> list[RuntimeEvent]:
    return [
        event
        for event in events
        if event.type == RuntimeEventType.STATUS_UPDATE and event.data.get("status") == IMAGES_NOT_SENT_STATUS
    ]


class TestImagePrompts:
    @pytest.mark.asyncio
    async def test_an_agent_that_advertises_image_prompts_receives_the_images_in_order(self, tmp_path: Path) -> None:
        first, first_body = _png(tmp_path, "a.png", 4_000)
        second, second_body = _png(tmp_path, "b.png", 9_000)
        pool = _pool(tmp_path, "--images")
        try:
            text, events = await _turn(pool, [str(first), str(second)])
        finally:
            await pool.close_all()

        assert "[echo] look at this" in text
        assert f"[images] {_digest(first_body)} {_digest(second_body)}" in text
        assert _not_sent_notices(events) == []

    @pytest.mark.asyncio
    async def test_an_image_of_the_largest_size_the_server_stages_arrives_whole(self, tmp_path: Path) -> None:
        image, body = _png(tmp_path, "big.png", 5 * 1024 * 1024)
        pool = _pool(tmp_path, "--images")
        try:
            text, events = await _turn(pool, [str(image)])
        finally:
            await pool.close_all()

        assert f"[images] {_digest(body)}" in text
        assert events[-1].type == RuntimeEventType.DONE

    @pytest.mark.asyncio
    async def test_an_agent_that_does_not_advertise_image_prompts_gets_the_text_and_the_turn_says_so(
        self, tmp_path: Path
    ) -> None:
        first, _ = _png(tmp_path, "a.png", 4_000)
        second, _ = _png(tmp_path, "b.png", 5_000)
        pool = _pool(tmp_path)
        try:
            text, events = await _turn(pool, [str(first), str(second)])
        finally:
            await pool.close_all()

        assert "[echo] look at this" in text
        assert "[images]" not in text
        assert events[-1].type == RuntimeEventType.DONE
        notices = _not_sent_notices(events)
        assert [notice.data.get("images") for notice in notices] == [2]
        assert events.index(notices[0]) < next(i for i, e in enumerate(events) if e.type == RuntimeEventType.TEXT_DELTA)

    @pytest.mark.asyncio
    async def test_a_turn_without_images_sends_the_text_alone(self, tmp_path: Path) -> None:
        pool = _pool(tmp_path, "--images")
        try:
            text, events = await _turn(pool, [])
        finally:
            await pool.close_all()

        assert "[echo] look at this" in text
        assert "[images]" not in text
        assert _not_sent_notices(events) == []


async def _stalled_turn(directory: Path) -> tuple[AcpRuntime, asyncio.Task[None], Process]:
    """A turn whose 5 MiB prompt sits half written in the pipe of an agent that no longer reads it."""
    image, _ = _png(directory, "big.png", 5 * 1024 * 1024)
    runtime = AcpRuntime(
        "stalled",
        RuntimeConfig(
            backend_type="acp",
            command=sys.executable,
            args=[str(_STALLED_AGENT), _STALL_SECONDS],
            cwd=str(directory),
            timeout_seconds=120,
        ),
    )

    async def consume() -> None:
        async for _ in runtime.run_turn("look", "chat-1", images=[str(image)]):
            pass

    turn = asyncio.create_task(consume())
    deadline = time.monotonic() + 20
    while getattr(runtime, "_session_id", None) is None:
        assert time.monotonic() < deadline, "the agent never created a session"
        await asyncio.sleep(0.05)
    await asyncio.sleep(1.0)
    process = getattr(runtime, "_process", None)
    assert process is not None
    return runtime, turn, process


async def _finish(runtime: AcpRuntime, turn: asyncio.Task[None], process: Process) -> None:
    turn.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await asyncio.wait_for(turn, timeout=20)
    with contextlib.suppress(ProcessLookupError):
        process.kill()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(runtime.close(), timeout=20)


class TestStalledAgent:
    @pytest.mark.asyncio
    async def test_cancel_ends_an_agent_that_stopped_reading_a_large_prompt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(stalled_agent, "STALLED_AGENT_TIMEOUT_SECONDS", 1.0)
        runtime, turn, process = await _stalled_turn(tmp_path)
        try:
            started = time.monotonic()
            await asyncio.wait_for(runtime.cancel("chat-1"), timeout=20)
            await asyncio.wait_for(process.wait(), timeout=10)

            assert time.monotonic() - started < 10
            assert process.returncode == -signal.SIGKILL
        finally:
            await _finish(runtime, turn, process)

    @pytest.mark.asyncio
    async def test_close_ends_an_agent_that_stopped_reading_a_large_prompt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(stalled_agent, "STALLED_AGENT_TIMEOUT_SECONDS", 1.0)
        runtime, turn, process = await _stalled_turn(tmp_path)
        try:
            turn.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(turn, timeout=20)
            started = time.monotonic()
            await asyncio.wait_for(runtime.close(), timeout=20)

            assert time.monotonic() - started < 10
            assert process.returncode is not None
        finally:
            await _finish(runtime, turn, process)

    @pytest.mark.asyncio
    async def test_a_healthy_agent_is_not_ended_by_cancel(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(stalled_agent, "STALLED_AGENT_TIMEOUT_SECONDS", 1.0)
        pool = _pool(tmp_path, "--images")
        try:
            await _turn(pool, [])
            runtime = pool.get("mock")
            process = getattr(runtime, "_process", None)
            assert process is not None

            await runtime.cancel("chat-1")
            await asyncio.sleep(0.2)

            assert process.returncode is None
        finally:
            await pool.close_all()
