"""A CLI that has not read its large prompt yet does not hold up the turn or its stop."""

from __future__ import annotations

import asyncio
import sys
import time

import pytest

from myrm_agent_harness.toolkits.acp.types import AcpErrorCode, RuntimeEventType

from ._fakes import FakeCli, errors_of, make_runtime, run_turn, types_of

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the CLI stand-ins are POSIX shebang scripts")

# Far beyond a pipe buffer, so the write is still pending while the CLI has not started reading.
_LARGE_PROMPT = "x" * 300_000


@pytest.mark.asyncio
async def test_a_stop_ends_a_turn_whose_cli_has_not_read_its_prompt_yet(fake_cli: FakeCli) -> None:
    fake_cli.set_scenario({"stall_before_stdin": 60})
    runtime = make_runtime(fake_cli)
    turn = asyncio.create_task(run_turn(runtime, _LARGE_PROMPT))
    async with asyncio.timeout(15):
        while not runtime.is_alive:
            await asyncio.sleep(0.02)
    await asyncio.sleep(0.5)

    started = time.monotonic()
    await runtime.cancel("s1")
    events = await asyncio.wait_for(turn, 15)

    assert time.monotonic() - started < 8
    assert [e.data["error"].code for e in errors_of(events)] == [AcpErrorCode.CANCELLED]
    assert runtime._process is not None and runtime._process.killed_by_us is True


@pytest.mark.asyncio
async def test_a_large_prompt_reaches_a_cli_that_starts_reading_late(fake_cli: FakeCli) -> None:
    fake_cli.set_scenario({"stall_before_stdin": 0.5, "text": "done"})

    events = await run_turn(make_runtime(fake_cli), _LARGE_PROMPT)

    assert not errors_of(events)
    assert types_of(events)[-1] is RuntimeEventType.DONE
    assert fake_cli.calls()[0]["prompt"] == _LARGE_PROMPT + "\n"
