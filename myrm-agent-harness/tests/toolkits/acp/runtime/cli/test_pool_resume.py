"""``RuntimePool`` driving a ``CliRuntime`` across turns.

A CLI backend spawns one process per turn; continuity between turns lives only in the CLI's own session id,
replayed through ``--resume``. This pins that the second pool turn resumes the session the first turn announced,
and that a oneshot turn in between neither reuses nor wipes it.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import AcpErrorCode, RuntimeConfig, RuntimeEvent

from ._fakes import FakeCli, errors_of, text_of

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the CLI stand-ins are POSIX shebang scripts")


@pytest.fixture
async def pool(fake_cli: FakeCli, tmp_path: Path) -> AsyncIterator[RuntimePool]:
    runtime_pool = RuntimePool(max_concurrent=2)
    runtime_pool.register(
        "claude",
        RuntimeConfig(
            backend_type="cli",
            command=str(fake_cli.command("claude")),
            args=["-p", "--output-format", "stream-json"],
            permission_mode="safe",
            cwd=str(tmp_path),
            timeout_seconds=20,
        ),
    )
    yield runtime_pool
    await runtime_pool.close_all()


async def _run_turn(
    runtime_pool: RuntimePool, *, mode: str = "persistent", session_id: str = "chat-1"
) -> list[RuntimeEvent]:
    return [e async for e in runtime_pool.run_turn("claude", "prompt", session_id=session_id, mode=mode)]


@pytest.mark.asyncio
async def test_second_turn_resumes_the_session_the_first_turn_announced(pool: RuntimePool, fake_cli: FakeCli) -> None:
    first = await _run_turn(pool)
    second = await _run_turn(pool)

    assert not errors_of(first)
    assert not errors_of(second)
    assert text_of(first)
    assert text_of(second) == text_of(first)
    assert fake_cli.resume_args() == [None, text_of(first)]


@pytest.mark.asyncio
async def test_oneshot_turn_starts_fresh_and_leaves_the_persistent_session_resumable(
    pool: RuntimePool, fake_cli: FakeCli
) -> None:
    """A fresh-session review between two persistent turns must not cost the chat its session."""
    first = text_of(await _run_turn(pool))
    oneshot = await _run_turn(pool, mode="oneshot", session_id="claude-oneshot-1")
    third = text_of(await _run_turn(pool))

    assert not errors_of(oneshot)
    assert text_of(oneshot) != first
    assert third == first
    assert fake_cli.resume_args() == [None, None, first]


@pytest.mark.asyncio
async def test_releasing_resident_backends_keeps_the_cli_resume_id(pool: RuntimePool, fake_cli: FakeCli) -> None:
    """Idle cleanup frees ACP processes; a CLI chat must still resume where it left off afterwards."""
    first = text_of(await _run_turn(pool))
    await pool.release_resident()
    second = text_of(await _run_turn(pool))

    assert second == first
    assert fake_cli.resume_args() == [None, first]


@pytest.mark.asyncio
async def test_stopping_a_turn_through_the_pool_ends_it_and_keeps_the_conversation(
    pool: RuntimePool, fake_cli: FakeCli
) -> None:
    first = text_of(await _run_turn(pool))
    fake_cli.set_scenario({"hang_before_output": True})
    turn = asyncio.create_task(_run_turn(pool))
    async with asyncio.timeout(15):
        while len(fake_cli.calls()) < 2:
            await asyncio.sleep(0.02)
    await asyncio.sleep(0.2)

    await pool.cancel("claude", "chat-1")
    stopped = await asyncio.wait_for(turn, 15)
    fake_cli.set_scenario({})
    after = text_of(await _run_turn(pool))

    assert [e.data["error"].code for e in errors_of(stopped)] == [AcpErrorCode.CANCELLED]
    assert after == first
