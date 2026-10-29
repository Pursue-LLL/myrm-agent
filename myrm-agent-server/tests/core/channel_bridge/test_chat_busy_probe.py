"""The IM chat a member is mid-conversation in is busy for a wake turn, and only a chat an IM turn has talked in is asked."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.channels.types import InboundMessage
from app.core.channel_bridge.wake_return import ChannelChatBusyProbe, WakeOrigins

_MSG = InboundMessage(channel="telegram", sender_id="u1", content="research it", chat_id="room-1")


def _probe(origins: WakeOrigins, *, busy: bool) -> tuple[ChannelChatBusyProbe, MagicMock]:
    gateway = MagicMock(is_session_busy=MagicMock(return_value=busy))
    return ChannelChatBusyProbe(gateway, origins), gateway


def test_the_chat_is_busy_when_the_router_runs_a_turn_for_the_conversation_it_was_last_talked_in() -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    probe, gateway = _probe(origins, busy=True)

    assert probe.is_busy("chat-db-1") is True

    (asked,) = gateway.is_session_busy.call_args.args
    assert (asked.channel, asked.sender_id, asked.chat_id) == ("telegram", "u1", "room-1")


def test_the_chat_is_free_when_the_router_runs_no_turn_for_the_conversation() -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    probe, _gateway = _probe(origins, busy=False)

    assert probe.is_busy("chat-db-1") is False


def test_a_chat_no_im_turn_talked_in_is_free_without_asking_the_router() -> None:
    probe, gateway = _probe(WakeOrigins(), busy=True)

    assert probe.is_busy("chat-db-1") is False
    gateway.is_session_busy.assert_not_called()
