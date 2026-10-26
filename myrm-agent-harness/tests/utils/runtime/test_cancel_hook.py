"""``on_token_cancelled``: a callback that fires within one poll interval of the token being cancelled."""

from __future__ import annotations

import asyncio

import pytest

from myrm_agent_harness.utils.runtime.cancel_hook import on_token_cancelled
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken


@pytest.mark.asyncio
async def test_the_callback_fires_soon_after_the_token_is_cancelled_while_the_block_keeps_running() -> None:
    token = CancellationToken("req-1")
    fired = asyncio.Event()

    async def callback() -> None:
        fired.set()

    async with on_token_cancelled(token, callback):
        assert not fired.is_set()
        token.cancel()
        async with asyncio.timeout(5):
            await fired.wait()


@pytest.mark.asyncio
async def test_the_callback_fires_once_however_long_the_block_lasts() -> None:
    token = CancellationToken("req-1")
    calls: list[int] = []

    async def callback() -> None:
        calls.append(1)

    async with on_token_cancelled(token, callback):
        token.cancel()
        await asyncio.sleep(0.8)

    assert calls == [1]


@pytest.mark.asyncio
async def test_a_token_that_is_never_cancelled_never_fires() -> None:
    token = CancellationToken("req-1")
    calls: list[int] = []

    async def callback() -> None:
        calls.append(1)

    async with on_token_cancelled(token, callback):
        await asyncio.sleep(0.4)

    assert calls == []


@pytest.mark.asyncio
async def test_a_cancellation_after_the_block_has_ended_fires_nothing() -> None:
    token = CancellationToken("req-1")
    calls: list[int] = []

    async def callback() -> None:
        calls.append(1)

    async with on_token_cancelled(token, callback):
        pass
    token.cancel()
    await asyncio.sleep(0.5)

    assert calls == []


@pytest.mark.asyncio
async def test_a_missing_token_is_a_plain_block() -> None:
    async def callback() -> None:
        raise AssertionError("must not run")

    async with on_token_cancelled(None, callback):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_a_failing_callback_never_breaks_the_guarded_block(caplog: pytest.LogCaptureFixture) -> None:
    token = CancellationToken("req-1")
    attempted = asyncio.Event()

    async def callback() -> None:
        attempted.set()
        raise RuntimeError("kill failed")

    with caplog.at_level("WARNING", logger="myrm_agent_harness.utils.runtime.cancel_hook"):
        async with on_token_cancelled(token, callback):
            token.cancel()
            async with asyncio.timeout(5):
                await attempted.wait()
            await asyncio.sleep(0.05)

    assert any("cancel_hook_failed" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_an_exception_in_the_block_still_stops_the_watcher() -> None:
    token = CancellationToken("req-1")
    calls: list[int] = []

    async def callback() -> None:
        calls.append(1)

    with pytest.raises(ValueError, match="boom"):
        async with on_token_cancelled(token, callback):
            raise ValueError("boom")
    token.cancel()
    await asyncio.sleep(0.5)

    assert calls == []
