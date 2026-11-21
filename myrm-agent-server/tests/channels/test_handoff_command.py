"""IM ``/handoff <channel>`` moves the conversation the sender is talking in to another platform, and says why when it cannot."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.i18n import get_text
from app.channels.routing.commands import RouterCommandsMixin
from app.channels.types import InboundMessage, OutboundMessage
from app.services.chat.handoff import HandoffResult

_MESSAGE = InboundMessage(channel="telegram", sender_id="u1", content="/handoff feishu", user_id="uid1")


class _Handoff:
    """The collaborators of ``/handoff`` beyond the router, recorded."""

    def __init__(self, session_key: AsyncMock, chat_lookup: AsyncMock, handoff: AsyncMock) -> None:
        self.session_key = session_key
        self.chat_lookup = chat_lookup
        self.handoff = handoff


@pytest.fixture
def collaborators() -> Iterator[_Handoff]:
    session_key = AsyncMock(return_value="telegram:u1")
    chat_lookup = AsyncMock(return_value=SimpleNamespace(id="chat-1"))
    handoff = AsyncMock(return_value=HandoffResult(success=True))
    with (
        patch("app.core.channel_bridge.command_session.resolve_command_session_key", session_key),
        patch("app.services.chat.chat_service.ChatService.get_channel_chat_by_key", chat_lookup),
        patch("app.services.chat.handoff.handoff_chat", handoff),
    ):
        yield _Handoff(session_key, chat_lookup, handoff)


async def _reply_to(target: str, msg: InboundMessage = _MESSAGE) -> str:
    host = MagicMock()
    host._bus.publish_outbound = AsyncMock()

    await RouterCommandsMixin._handle_handoff_command(host, msg, target)

    host._bus.publish_outbound.assert_awaited_once()
    reply: OutboundMessage = host._bus.publish_outbound.await_args.args[0]
    return reply.content


async def test_the_conversation_the_command_resolves_is_the_one_handed_off(collaborators: _Handoff) -> None:
    reply = await _reply_to("feishu")

    collaborators.session_key.assert_awaited_once_with(_MESSAGE)
    collaborators.chat_lookup.assert_awaited_once_with("telegram:u1")
    collaborators.handoff.assert_awaited_once_with("chat-1", "feishu")
    assert reply == get_text(_MESSAGE, "handoff_success", target="feishu")


async def test_a_handoff_needs_a_target(collaborators: _Handoff) -> None:
    assert await _reply_to("  ") == get_text(_MESSAGE, "handoff_no_target")
    collaborators.handoff.assert_not_awaited()


async def test_a_handoff_to_the_channel_the_sender_is_on_is_refused(collaborators: _Handoff) -> None:
    assert await _reply_to("telegram") == get_text(_MESSAGE, "handoff_same_channel")
    collaborators.handoff.assert_not_awaited()


async def test_a_chat_without_a_conversation_has_nothing_to_hand_off(collaborators: _Handoff) -> None:
    collaborators.chat_lookup.return_value = None

    assert await _reply_to("feishu") == get_text(_MESSAGE, "handoff_failed", error="No active session")
    collaborators.handoff.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "key", "words_the_target"),
    [
        pytest.param("Target channel not found", "handoff_channel_not_found", True, id="unknown-channel"),
        pytest.param("Target channel is not connected", "handoff_channel_not_found", True, id="channel-not-connected"),
        pytest.param("No pairing for this user", "handoff_no_pairing", True, id="not-paired"),
        pytest.param("The disk is full", "handoff_failed", False, id="any-other-failure"),
    ],
)
async def test_a_refused_handoff_says_which_of_its_causes_it_was(
    collaborators: _Handoff, error: str, key: str, words_the_target: bool
) -> None:
    collaborators.handoff.return_value = HandoffResult(success=False, error=error)

    expected = get_text(_MESSAGE, key, target="feishu") if words_the_target else get_text(_MESSAGE, key, error=error)
    assert await _reply_to("feishu") == expected
