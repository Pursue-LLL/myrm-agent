"""Draft-review turns must not show the agent's reply before a human approved it.

A held reply reaches the chat only through the approval flow, so the live streaming edits of the chat
placeholder must not carry it - on a first turn and on a resumed turn alike. Progress text keeps showing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.router import AgentRouter
from app.channels.routing.router_execution import RouterExecutionMixin
from app.channels.routing.router_models import _ActiveTask, _AgentTurnScratch, _RouterExecutionContext
from app.channels.types import (
    InboundMessage,
    OutboundMessage,
    ProgressUpdate,
    ReplyMode,
    StreamingText,
    TopicContext,
)

_REPLY = "Your refund of $500 is approved, and we also owe you a 20% discount."


class _ScriptedExecutor:
    """Yields the event sequence of a real channel turn: progress, growing streamed text, final reply."""

    async def execute_stream(self, msg: InboundMessage, user_id: str, **_: object) -> AsyncIterator[object]:
        yield ProgressUpdate(label="Looking up your order")
        yield StreamingText(text=_REPLY[:30])
        yield StreamingText(text=_REPLY)
        yield OutboundMessage(channel=msg.channel, recipient_id=msg.chat_id or "", content=_REPLY, user_id=user_id)


def _inbound() -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", content="where is my refund?", chat_id="chat-1", message_id="m1")


class _Chat:
    """What the customer's chat saw: placeholder edits plus the activity pings that wake the placeholder."""

    def __init__(self, router: AgentRouter, monkeypatch: pytest.MonkeyPatch) -> None:
        self.router = router
        self.edits: list[str] = []
        self.activity = AsyncMock()
        self.progress = AsyncMock(return_value=None)

        async def record_edit(
            channel: str, chat_id: str, placeholder_id: str | None, text: str, *_: object, **__: object
        ) -> bool:
            self.edits.append(text)
            return True

        monkeypatch.setattr(router, "_try_edit_with_retry", record_edit)
        monkeypatch.setattr(router, "_try_throttled_edit", self.progress)
        monkeypatch.setattr(router, "_resolve_live_placeholder_id", lambda state_key: "placeholder-1")
        monkeypatch.setattr(router, "_mark_deferred_placeholder_activity", self.activity)
        monkeypatch.setattr("app.channels.routing.router_stream.run_reassurance_loop", AsyncMock())

    async def stream(self, *, hold_reply: bool) -> OutboundMessage | None:
        result, _ = await self.router._consume_executor_stream(
            _inbound(), "guest_u1", "telegram:chat-1", "chat-1", hold_reply=hold_reply
        )
        return result


@pytest.fixture
def chat(monkeypatch: pytest.MonkeyPatch) -> _Chat:
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=None)
    router = AgentRouter(bus=bus, pairing_store=MagicMock(), agent_executor=_ScriptedExecutor())
    return _Chat(router, monkeypatch)


async def test_held_reply_text_never_reaches_the_chat_placeholder(chat: _Chat) -> None:
    result = await chat.stream(hold_reply=True)

    assert chat.edits == []
    assert result is not None and result.content == _REPLY  # still handed to the approval draft
    assert chat.progress.await_count == 1  # progress text keeps showing
    assert chat.activity.await_count == 3  # and every event still wakes the deferred placeholder


async def test_reply_that_is_not_held_still_streams_into_the_placeholder(chat: _Chat) -> None:
    await chat.stream(hold_reply=False)

    assert any(_REPLY in edit for edit in chat.edits)


class _TurnHost(RouterExecutionMixin):
    """The execution mixin with the collaborators of one turn replaced by recorders."""

    def __init__(self) -> None:
        self._active_tasks: dict[str, _ActiveTask] = {}
        self._bus = MagicMock(get_channel=MagicMock(return_value=None))
        self.stream_kwargs: dict[str, object] = {}
        self.deliver_kwargs: dict[str, object] = {}

    async def _setup_message_effects(self, *_: object) -> None:
        return None

    async def _consume_executor_stream(self, *_: object, **kwargs: object) -> tuple[OutboundMessage | None, float]:
        self.stream_kwargs = kwargs
        return None, 0.0

    async def _deliver_agent_result(self, *_: object, **kwargs: object) -> bool:
        self.deliver_kwargs = kwargs
        return True

    def _resolve_live_placeholder_id(self, state_key: str) -> str | None:
        return None

    async def _cleanup_effects(self, *_: object) -> None:
        return None


@pytest.mark.parametrize(
    ("reply_mode", "is_resume", "expect_hold"),
    [
        (ReplyMode.DRAFT_REVIEW, False, True),
        (ReplyMode.DRAFT_REVIEW, True, True),
        (ReplyMode.AUTO, False, False),
        (ReplyMode.AUTO, True, False),
        (None, False, False),
    ],
    ids=["draft-first-turn", "draft-resumed-turn", "auto-first-turn", "auto-resumed-turn", "no-topic"],
)
async def test_the_hold_follows_the_topic_and_not_the_kind_of_turn(
    reply_mode: ReplyMode | None, is_resume: bool, expect_hold: bool
) -> None:
    """A resumed turn passes no topic to the stream consumer, so the hold cannot depend on that argument."""
    host = _TurnHost()
    topic = TopicContext(topic_id="topic-1", reply_mode=reply_mode) if reply_mode is not None else None
    ctx = _RouterExecutionContext(
        user_id="guest_u1",
        state_key="telegram:chat-1",
        chat_id="chat-1",
        message_id="m1",
        topic_ctx=topic,
        exec_msg=_inbound(),
    )

    await host._execute_prepared_context(ctx, _AgentTurnScratch(), is_resume=is_resume, inbound_had_voice=False)  # type: ignore[arg-type]

    assert host.stream_kwargs["hold_reply"] is expect_hold
    assert host.stream_kwargs["topic_context"] is (None if is_resume else topic)
    assert host.deliver_kwargs["topic_ctx"] is topic
