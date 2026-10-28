"""Group chatter that arrives while the chat's turn runs is settled at once instead of queued behind that turn.

Queued, a message nobody addressed to the bot takes one of the pending slots, makes the chat read "Agent is busy, your
message has been queued" and still ends as context for the next turn. Runs on the real ``AgentRouter``, session gate
and policy resolver: the turn is held by the executor, so the chat is really busy.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.bus import MessageBus
from app.channels.i18n import get_text
from app.channels.protocols.pairing import DmPolicy, GroupPolicy, GroupTriggerMode, PairingStatus
from app.channels.routing.policy_resolver_support import GroupFollowUpTracker, should_respond_in_group_support
from app.channels.routing.router import AgentRouter
from app.channels.routing.session_gate import SessionGateConfig, gate_key
from app.channels.types import InboundMessage, MediaAttachment, MediaType, OutboundMessage

_CHAT = "g1"
_RECORD_INBOUND = "app.channels.routing.channel_data_plane.ChannelDataPlaneService.record_inbound"


class _Pairing:
    async def resolve(self, channel: str, sender_id: str) -> str | None:
        return None

    async def bind(self, channel: str, sender_id: str, user_id: str, *, status: PairingStatus = PairingStatus.ACTIVE) -> None:
        return None

    async def unbind(self, channel: str, sender_id: str) -> None:
        return None

    async def get_status(self, channel: str, sender_id: str) -> PairingStatus | None:
        return None

    async def get_pairing_detail(self, channel: str, sender_id: str) -> None:
        return None


class _Policy:
    """A group that answers to the prefix ``/ask `` and nothing else."""

    def __init__(self) -> None:
        self.enabled = {_CHAT}
        self.group_policy = GroupPolicy.OPEN

    async def get_dm_policy(self, channel: str) -> DmPolicy:
        return DmPolicy.OPEN

    async def get_group_policy(self, channel: str) -> GroupPolicy:
        return self.group_policy

    async def get_group_trigger(self, channel: str) -> tuple[GroupTriggerMode, list[str]]:
        return GroupTriggerMode.PREFIX, ["/ask "]

    async def get_enabled_groups(self) -> set[str]:
        return self.enabled

    async def get_guest_mode(self, channel: str) -> bool:
        return False

    async def get_default_user_id(self) -> str | None:
        return "owner"


def _group(content: str, sender: str = "alice", *, media: tuple[MediaAttachment, ...] = ()) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id=sender,
        chat_id=_CHAT,
        is_group=True,
        content=content,
        media=media,
        metadata={"locale": "en"},
    )


class _Chat:
    """A group chat whose first turn is held by the executor until ``release`` is set."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.turns: list[InboundMessage] = []
        self.recorded = AsyncMock()
        self.policy = _Policy()
        self.bus = MessageBus()
        self.bus.publish_outbound = AsyncMock()  # type: ignore[method-assign]
        executor = MagicMock()
        executor.execute_stream = self._stream
        self.router = AgentRouter(
            self.bus,
            _Pairing(),  # type: ignore[arg-type]
            executor,
            self.policy,  # type: ignore[arg-type]
            session_gate_config=SessionGateConfig(debounce_window_ms=20, max_pending_per_session=10),
        )
        self.key = gate_key(_group("x"))

    async def _stream(self, msg: InboundMessage, user_id: str, **_: object) -> AsyncGenerator[OutboundMessage, None]:
        self.turns.append(msg)
        if len(self.turns) == 1:
            await self.release.wait()
        yield OutboundMessage(channel=msg.channel, recipient_id=msg.chat_id, content="ok", user_id=user_id)

    async def start_busy_turn(self) -> None:
        await self.router._dispatch_inbound_message(_group("/ask hold"))
        await asyncio.sleep(0.2)
        assert self.router._gate.running_turn(self.key) > 0

    async def say(self, msg: InboundMessage) -> None:
        await self.router._dispatch_inbound_message(msg)
        await asyncio.sleep(0.05)

    def pending(self) -> int:
        return self.router._gate.pending_count(self.key)

    def busy_acks(self) -> int:
        ack = get_text(_group("x"), "busy_ack_queued", position=1, max_pending=10)
        full = get_text(_group("x"), "busy_ack_queue_full")
        sent = [call.args[0].content for call in self.bus.publish_outbound.await_args_list]
        return sum(content in (ack, full) or content.startswith("✅ Received!") for content in sent)

    def recorded_chatter(self, content: str) -> list[dict[str, object]]:
        """The ledger writes of the message with this text, as the keyword arguments they were made with."""
        return [call.kwargs for call in self.recorded.await_args_list if call.args[0].content == content]

    def context_of_the_next_turn(self) -> list[str]:
        return [entry.content for entry in self.turns[-1].context_messages]

    async def finish_and_ask_again(self) -> None:
        self.release.set()
        await asyncio.sleep(0.2)
        await self.router._dispatch_inbound_message(_group("/ask next"))
        await asyncio.sleep(0.4)


@pytest.fixture
async def chat() -> AsyncGenerator[_Chat, None]:
    held = _Chat()
    with patch(_RECORD_INBOUND, new=held.recorded):
        yield held
    held.release.set()
    await asyncio.sleep(0.1)
    held.router._gate.clear()


async def test_chatter_during_a_busy_turn_does_not_take_a_pending_slot(chat: _Chat) -> None:
    await chat.start_busy_turn()

    await chat.say(_group("anyone for lunch?", "bob"))

    assert chat.pending() == 0


async def test_chatter_during_a_busy_turn_is_not_acknowledged_as_queued(chat: _Chat) -> None:
    await chat.start_busy_turn()

    await chat.say(_group("anyone for lunch?", "bob"))

    assert chat.busy_acks() == 0


async def test_chatter_during_a_busy_turn_becomes_context_of_the_next_turn(chat: _Chat) -> None:
    await chat.start_busy_turn()
    await chat.say(_group("anyone for lunch?", "bob"))

    await chat.finish_and_ask_again()

    assert len(chat.turns) == 2
    assert chat.context_of_the_next_turn() == ["anyone for lunch?"]


async def test_chatter_during_a_busy_turn_is_recorded_once_as_a_non_trigger(chat: _Chat) -> None:
    await chat.start_busy_turn()
    await chat.say(_group("anyone for lunch?", "bob"))
    await chat.finish_and_ask_again()

    assert chat.recorded_chatter("anyone for lunch?") == [{"is_trigger": False}]


async def test_a_message_that_addresses_the_bot_still_queues_behind_the_turn(chat: _Chat) -> None:
    await chat.start_busy_turn()

    await chat.say(_group("/ask and this too", "bob"))

    assert chat.pending() == 1
    assert chat.busy_acks() == 1


async def test_a_message_with_an_attachment_still_queues_behind_the_turn(chat: _Chat) -> None:
    await chat.start_busy_turn()
    photo = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.invalid/a.png")

    await chat.say(_group("look at this", "bob", media=(photo,)))

    assert chat.pending() == 1


@pytest.mark.parametrize("closed_by", ["group_disabled", "chat_not_enabled"])
async def test_a_chat_the_policy_no_longer_admits_keeps_the_normal_path(chat: _Chat, closed_by: str) -> None:
    await chat.start_busy_turn()
    if closed_by == "group_disabled":
        chat.policy.group_policy = GroupPolicy.DISABLED
    else:
        chat.policy.enabled.clear()

    await chat.say(_group("anyone for lunch?", "bob"))

    assert chat.pending() == 1


async def test_chatter_while_the_chat_is_idle_takes_the_normal_path_and_is_recorded_once(chat: _Chat) -> None:
    await chat.router._dispatch_inbound_message(_group("anyone for lunch?", "bob"))
    await asyncio.sleep(0.4)

    assert chat.recorded_chatter("anyone for lunch?") == [{"is_trigger": False}]
    assert chat.turns == []


async def test_an_answer_to_a_suspended_run_is_never_settled_as_chatter(chat: _Chat) -> None:
    await chat.start_busy_turn()
    answer = dataclasses.replace(_group("yes", "bob"), resume_value={"approved": True})

    await chat.say(answer)

    assert chat.pending() == 1


async def test_the_chatter_check_is_not_made_while_the_chat_is_idle(chat: _Chat) -> None:
    chat.router._resolver.divert_group_chatter = AsyncMock(return_value=True)  # type: ignore[method-assign]

    await chat.say(_group("anyone for lunch?", "bob"))

    chat.router._resolver.divert_group_chatter.assert_not_awaited()


async def test_a_failing_chatter_check_queues_the_message_as_before(chat: _Chat) -> None:
    await chat.start_busy_turn()
    chat.router._resolver.divert_group_chatter = AsyncMock(side_effect=RuntimeError("policy store down"))  # type: ignore[method-assign]

    await chat.say(_group("anyone for lunch?", "bob"))

    assert chat.pending() == 1


# --- the read-only trigger check -------------------------------------------------------------------------------------


async def test_checking_a_mute_word_without_committing_leaves_the_thread_and_the_chat_alone() -> None:
    tracker = GroupFollowUpTracker(ttl_seconds=600.0, max_size=10)
    tracker.activate("telegram:g1:t1")
    fx = MagicMock(send_mute_reply=AsyncMock())
    msg = InboundMessage(channel="telegram", sender_id="bob", chat_id="g1", is_group=True, content="/mute", thread_id="t1")

    responds, text = await should_respond_in_group_support(_Policy(), tracker, fx, msg, commit=False)  # type: ignore[arg-type]

    assert (responds, text) == (True, "___MUTE_CONFIRMED___")
    assert tracker.is_active("telegram:g1:t1")
    fx.send_mute_reply.assert_not_awaited()


async def test_committing_a_mute_word_mutes_the_thread_and_tells_the_chat() -> None:
    tracker = GroupFollowUpTracker(ttl_seconds=600.0, max_size=10)
    tracker.activate("telegram:g1:t1")
    fx = MagicMock(send_mute_reply=AsyncMock())
    msg = InboundMessage(channel="telegram", sender_id="bob", chat_id="g1", is_group=True, content="/mute", thread_id="t1")

    with patch("app.channels.routing.follow_up.mute_tracked_thread"):
        responds, text = await should_respond_in_group_support(_Policy(), tracker, fx, msg)  # type: ignore[arg-type]

    assert (responds, text) == (True, "___MUTE_CONFIRMED___")
    assert not tracker.is_active("telegram:g1:t1")
    fx.send_mute_reply.assert_awaited_once()
