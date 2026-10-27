"""A chat reader never sees the model's reasoning stage, whatever the shipped stream gate lets through.

The real coordinator decides what reaches the chat, so these tests stream scripted text events through an
``AgentRouter`` and read back the edits it would have sent. Text that is only reasoning so far produces no edit
at all; reasoning that follows or accompanies an answer leaves that answer's edits as they were.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage, OutboundMessage, StreamingText

if TYPE_CHECKING:
    from app.channels.protocols.agent import AgentExecutor

_ANSWER = "Your refund is approved and will reach your card within five days of today."
_THINKING_ONLY = "<think>I should look up the order before answering"


class _Executor:
    """Plays one turn whose text events are exactly the scripted ones."""

    def __init__(self, texts: list[str]) -> None:
        self._texts = texts

    async def execute_stream(self, msg: InboundMessage, user_id: str, **_: object) -> AsyncIterator[object]:
        for text in self._texts:
            yield StreamingText(text=text)
        yield OutboundMessage(channel=msg.channel, recipient_id=msg.chat_id or "", content=_ANSWER, user_id=user_id)


def _router(monkeypatch: pytest.MonkeyPatch, texts: list[str]) -> tuple[AgentRouter, AsyncMock]:
    """A real router and a real stream coordinator; only the chat edits are recorded instead of sent."""
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=None)
    router = AgentRouter(bus=bus, pairing_store=MagicMock(), agent_executor=cast("AgentExecutor", _Executor(texts)))
    edit_progress = AsyncMock(return_value=True)
    monkeypatch.setattr(router._fx, "edit_progress", edit_progress)
    monkeypatch.setattr(router, "_try_throttled_edit", AsyncMock(return_value=None))
    monkeypatch.setattr(router, "_resolve_live_placeholder_id", lambda state_key: "placeholder-1")
    monkeypatch.setattr(router, "_mark_deferred_placeholder_activity", AsyncMock())
    monkeypatch.setattr("app.channels.routing.router_stream.run_reassurance_loop", AsyncMock())
    return router, edit_progress


async def _edits_for(monkeypatch: pytest.MonkeyPatch, texts: list[str]) -> list[str]:
    router, edit_progress = _router(monkeypatch, texts)
    inbound = InboundMessage(channel="telegram", sender_id="u1", content="where is my refund?", chat_id="chat-1", message_id="m1")
    await router._consume_executor_stream(inbound, "guest_u1", "telegram:chat-1", "chat-1")
    return [call.args[3] for call in edit_progress.await_args_list]


async def test_text_that_is_only_reasoning_produces_no_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    edits = await _edits_for(monkeypatch, [_THINKING_ONLY, _THINKING_ONLY + " and then the carrier"])

    assert edits == []


async def test_reasoning_before_the_answer_leaves_only_the_answer_in_the_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    edits = await _edits_for(monkeypatch, [_THINKING_ONLY, f"{_THINKING_ONLY}</think>{_ANSWER}"])

    assert len(edits) == 1
    assert edits[0].startswith(_ANSWER)
    assert "\U0001f4ad" not in edits[0]
    assert "<think>" not in edits[0]


async def test_reasoning_after_the_answer_started_adds_no_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    edits = await _edits_for(monkeypatch, [_ANSWER, "<think>now I check the shipping carrier"])

    assert len(edits) == 1
    assert edits[0].startswith(_ANSWER)
    assert "\U0001f4ad" not in edits[0]


async def test_an_answer_with_reasoning_still_open_is_sent_without_a_progress_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    edits = await _edits_for(monkeypatch, [f"{_ANSWER} <think>one more thing to verify"])

    assert edits == [_ANSWER]
