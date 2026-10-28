"""What a user sees on their message across a whole turn: the platform's own reaction calls, in order.

Runs the real ``_handle_merged`` and the real ``_execute_prepared_context`` (with the run itself scripted) over a
Telegram-shaped channel, where a reaction replaces the previous one. A turn is one received mark and exactly one
verdict, so the platform is asked once to mark, once to take the mark off and once to show the verdict; a failed turn
says why in words before it is marked.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.registry import get_channel_class
from app.channels.routing.router import AgentRouter
from app.channels.routing.router_models import _RouterExecutionContext
from app.channels.types import InboundMessage, OutboundMessage

EYES = "\U0001f440"
THUMBS_UP = "\U0001f44d"
CRYING = "\U0001f622"
CLEARED = ""

Run = Callable[..., Awaitable[tuple[OutboundMessage | None, float]]]


def _inbound() -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", chat_id="chat-1", content="hi", message_id="m1")


def _world(run: Run) -> tuple[AgentRouter, list[tuple[str, str]]]:
    """A router over a Telegram-shaped channel; the log holds every reaction call and every reply, in order."""
    log: list[tuple[str, str]] = []

    async def react(_chat_id: str, _message_id: str, emoji: str) -> None:
        log.append(("react", emoji))

    async def publish(outbound: OutboundMessage) -> None:
        log.append(("reply", outbound.content))

    channel = MagicMock()
    channel.capabilities = get_channel_class("telegram").capabilities
    channel.react_to_message = react
    channel.stop_typing = AsyncMock()
    channel.read_context_document = AsyncMock(return_value=None)
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=channel)
    bus.publish_outbound = AsyncMock(side_effect=publish)
    router = AgentRouter(bus=bus, pairing_store=MagicMock(), agent_executor=MagicMock())
    inbound = _inbound()
    ctx = _RouterExecutionContext(
        user_id="u1", state_key="telegram:chat-1", chat_id="chat-1", message_id="m1", topic_ctx=None, exec_msg=inbound
    )
    router._prepare_execution_context = AsyncMock(return_value=ctx)  # type: ignore[method-assign]
    router._retire_open_approval = AsyncMock()  # type: ignore[method-assign]
    router._setup_message_effects = AsyncMock(return_value=None)  # type: ignore[method-assign]
    router._deliver_agent_result = AsyncMock(return_value=True)  # type: ignore[method-assign]
    router._consume_executor_stream = AsyncMock(side_effect=run)  # type: ignore[method-assign]
    router._gate = MagicMock()
    return router, log


def _reactions(log: list[tuple[str, str]]) -> list[str]:
    return [what for kind, what in log if kind == "react"]


async def _answer(*_: object, **__: object) -> tuple[OutboundMessage | None, float]:
    return None, 0.0


async def _break(*_: object, **__: object) -> tuple[OutboundMessage | None, float]:
    raise RuntimeError("model unavailable")


@pytest.mark.asyncio
async def test_a_completed_turn_marks_takes_the_mark_off_and_shows_the_result_once_each() -> None:
    router, log = _world(_answer)

    await router._handle_merged(_inbound())

    assert _reactions(log) == [EYES, CLEARED, THUMBS_UP]


@pytest.mark.asyncio
async def test_a_failed_turn_tells_the_user_in_words_before_the_mark_comes_off() -> None:
    router, log = _world(_break)

    await router._handle_merged(_inbound())

    reply_at = next(i for i, (kind, _) in enumerate(log) if kind == "reply")
    assert _reactions(log) == [EYES, CLEARED, CRYING]
    assert reply_at < log.index(("react", CLEARED)) < log.index(("react", CRYING))


@pytest.mark.asyncio
async def test_a_stopped_turn_leaves_no_mark_and_no_verdict() -> None:
    started = asyncio.Event()

    async def hang(*_: object, **__: object) -> tuple[OutboundMessage | None, float]:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    router, log = _world(hang)
    turn = asyncio.create_task(router._handle_merged(_inbound()))
    await started.wait()

    turn.cancel()
    await turn

    assert _reactions(log) == [EYES, CLEARED]


@pytest.mark.asyncio
async def test_the_agent_starts_before_the_platform_has_answered_the_mark() -> None:
    release = asyncio.Event()
    mark_answered_when_run_began: list[bool] = []
    answered: list[str] = []

    async def run(*_: object, **__: object) -> tuple[OutboundMessage | None, float]:
        mark_answered_when_run_began.append(bool(answered))
        release.set()
        return None, 0.0

    router, log = _world(run)

    async def slow_react(_chat_id: str, _message_id: str, emoji: str) -> None:
        if emoji == EYES:
            await release.wait()
            answered.append(emoji)
        log.append(("react", emoji))

    router._bus.get_channel("telegram").react_to_message = slow_react

    await asyncio.wait_for(router._handle_merged(_inbound()), timeout=5)

    assert mark_answered_when_run_began == [False]
    assert _reactions(log) == [EYES, CLEARED, THUMBS_UP]


@pytest.mark.asyncio
async def test_a_turn_cancelled_while_the_platform_is_slow_leaves_no_request_running() -> None:
    mark_started = asyncio.Event()
    mark_cancelled = asyncio.Event()

    async def hang(*_: object, **__: object) -> tuple[OutboundMessage | None, float]:
        await mark_started.wait()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    router, log = _world(hang)

    async def unresponsive_react(_chat_id: str, _message_id: str, emoji: str) -> None:
        if emoji == EYES:
            mark_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                mark_cancelled.set()
                raise
        log.append(("react", emoji))

    router._bus.get_channel("telegram").react_to_message = unresponsive_react
    turn = asyncio.create_task(router._handle_merged(_inbound()))
    await mark_started.wait()

    turn.cancel()  # the user stops the turn; settling it now waits for the platform
    await asyncio.sleep(0.05)
    assert not turn.done()
    turn.cancel()  # the service shuts down while the platform is still silent
    with pytest.raises(asyncio.CancelledError):
        await turn

    assert mark_cancelled.is_set()
