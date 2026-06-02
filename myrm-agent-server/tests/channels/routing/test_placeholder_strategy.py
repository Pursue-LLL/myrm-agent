"""Adaptive placeholder defer + short-circuit."""

from __future__ import annotations

import asyncio

import pytest

from app.channels.routing.placeholder_strategy import (
    DEFER_SECONDS,
    DeferredPlaceholder,
    qualifies_short_circuit,
    utf16_len,
)
from app.channels.types import OutboundMessage


def _outbound(content: str, *, tool_steps: tuple[object, ...] = ()) -> OutboundMessage:
    return OutboundMessage(
        channel="telegram",
        recipient_id="1",
        content=content,
        user_id="u1",
        tool_steps=tool_steps,  # type: ignore[arg-type]
    )


def test_utf16_len_matches_telegram_units() -> None:
    assert utf16_len("a") == 1
    assert utf16_len("😀") == 2


def test_short_circuit_requires_no_tool_steps() -> None:
    short = "x" * 100
    assert qualifies_short_circuit(_outbound(short)) is True
    assert qualifies_short_circuit(_outbound(short, tool_steps=(object(),))) is False


@pytest.mark.asyncio
async def test_defer_waits_before_send() -> None:
    sent_at: list[float] = []

    async def send() -> str:
        sent_at.append(asyncio.get_event_loop().time())
        return "ph-1"

    start = asyncio.get_event_loop().time()
    deferred = DeferredPlaceholder()
    deferred.start(send)
    pid = await deferred.wait_for_id()
    elapsed = sent_at[0] - start
    assert pid == "ph-1"
    assert elapsed >= DEFER_SECONDS * 0.9


@pytest.mark.asyncio
async def test_short_circuit_cancels_deferred_placeholder() -> None:
    send_called = False

    async def send() -> str:
        nonlocal send_called
        send_called = True
        return "ph-1"

    deferred = DeferredPlaceholder()
    deferred.start(send)
    resolved = await deferred.resolve_for_delivery(_outbound("quick reply"))
    assert resolved is None
    assert send_called is False
