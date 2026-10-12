"""Draft-review turns: the whole reply is held for approval, and a reply that cannot be held is never sent.

``reply_mode=draft_review`` is a promise to the topic owner that no agent reply reaches the channel before a
human approved it, so holding the reply must keep everything the agent produced and must fail closed.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.routing.router_execution import RouterExecutionMixin
from app.channels.types import (
    ActionButton,
    DraftTimeoutAction,
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    ReplyMode,
    TopicContext,
)
from app.services.approvals.registry import ApprovalRegistry, send_outbound_draft_payload
from tests.channels.core.outbound_testkit import make_ephemeral_doc

_HANDOFF_BUTTON = ActionButton(label="Continue in browser", action_id="web:continue_chat", url="https://example.test/chat/abc")
_TOPIC = TopicContext(
    topic_id="topic-1",
    agent_id="agent-1",
    reply_mode=ReplyMode.DRAFT_REVIEW,
    draft_timeout_action=DraftTimeoutAction.AUTO_REJECT,
)


def _inbound() -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", content="send me the report", message_id="m1")


def _reply(tmp_path: Path, *media: MediaAttachment) -> OutboundMessage:
    report = tmp_path / "report.pdf"
    report.write_bytes(b"%PDF")
    return OutboundMessage(
        channel="telegram",
        recipient_id="chat1",
        content="Here is the report",
        user_id="owner-1",
        media=(MediaAttachment(media_type=MediaType.DOCUMENT, path=str(report)), *media),
        reply_to_id="m1",
        thread_id="th-7",
        metadata={"locale": "zh"},
    )


async def _attach_handoff(result: OutboundMessage, chat_id: str, msg: InboundMessage) -> OutboundMessage:
    return dataclasses.replace(result, components=result.components + ((_HANDOFF_BUTTON,),))


@pytest.fixture
def router() -> Iterator[tuple[RouterExecutionMixin, AsyncMock, AsyncMock]]:
    fx, bus = AsyncMock(), AsyncMock()
    mixin = RouterExecutionMixin()
    mixin._fx = fx  # type: ignore[attr-defined]
    mixin._bus = bus  # type: ignore[attr-defined]
    mixin._voice = None  # type: ignore[attr-defined]
    with patch.object(RouterExecutionMixin, "_attach_web_handoff", new=AsyncMock(side_effect=_attach_handoff)):
        yield mixin, fx, bus


async def _deliver(mixin: RouterExecutionMixin, result: OutboundMessage, *, placeholder_id: str | None = None) -> bool:
    deferred = AsyncMock()
    deferred.resolve_for_delivery = AsyncMock(return_value=placeholder_id)
    return await mixin._deliver_agent_result(
        result=result,
        deferred=deferred,
        msg=_inbound(),
        chat_id="chat1",
        last_progress_at=0.0,
        inbound_had_voice=False,
        topic_ctx=_TOPIC,
    )


async def test_draft_holds_the_whole_reply_and_sends_nothing(
    router: tuple[RouterExecutionMixin, AsyncMock, AsyncMock], tmp_path: Path
) -> None:
    """A reply with a screenshot, a file and the browser button is held whole as one draft; nothing reaches the channel."""
    mixin, _fx, bus = router
    shot = make_ephemeral_doc("shot.png")
    reply = _reply(tmp_path, shot)

    with patch.object(ApprovalRegistry, "create_approval", new=AsyncMock()) as create:
        delivered = await _deliver(mixin, reply)

    assert delivered is False
    bus.publish_outbound.assert_not_called()
    create.assert_awaited_once()
    payload = create.await_args.kwargs["payload"]
    held = OutboundMessage.from_dict(json.loads(json.dumps(payload["outbound"])))
    assert payload["draft_content"] == "Here is the report"
    assert "draft_media" not in payload
    assert held.media == reply.media
    assert held.components == ((_HANDOFF_BUTTON,),)
    assert (held.thread_id, held.reply_to_id, held.user_id) == ("th-7", "m1", "owner-1")
    Path(shot.path).unlink(missing_ok=True)


async def test_approved_draft_is_sent_exactly_as_the_agent_wrote_it(
    router: tuple[RouterExecutionMixin, AsyncMock, AsyncMock], tmp_path: Path
) -> None:
    mixin, _fx, _bus = router
    reply = _reply(tmp_path)

    with patch.object(ApprovalRegistry, "create_approval", new=AsyncMock()) as create:
        await _deliver(mixin, reply)
    stored = json.loads(json.dumps(create.await_args.kwargs["payload"]))  # what the approval record persists

    gateway = AsyncMock()
    with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway):
        assert await send_outbound_draft_payload(stored, "agent-1", "rec-1") is True

    sent = gateway.publish.await_args.args[0]
    assert sent.content == reply.content
    assert sent.media == reply.media
    assert sent.components == ((_HANDOFF_BUTTON,),)
    assert (sent.channel, sent.recipient_id, sent.user_id) == ("telegram", "chat1", "owner-1")
    assert (sent.thread_id, sent.reply_to_id) == ("th-7", "m1")
    assert reply.metadata is not None and reply.metadata.items() <= (sent.metadata or {}).items()


async def test_failing_to_hold_the_reply_withholds_it(
    router: tuple[RouterExecutionMixin, AsyncMock, AsyncMock], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    mixin, fx, bus = router
    shot = make_ephemeral_doc("shot.png")

    with (
        patch.object(ApprovalRegistry, "create_approval", new=AsyncMock(side_effect=RuntimeError("database is locked"))),
        caplog.at_level(logging.ERROR),
    ):
        delivered = await _deliver(mixin, _reply(tmp_path, shot), placeholder_id="ph_1")

    assert delivered is False
    bus.publish_outbound.assert_not_called()
    fx.edit_placeholder.assert_not_called()
    fx.cleanup_placeholder.assert_awaited_once_with("telegram", "chat1", "ph_1", "\u200b")
    assert not Path(shot.path).exists()
    assert any(r.levelno == logging.ERROR for r in caplog.records)
