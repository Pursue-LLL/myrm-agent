"""A turn belongs to one sender, and a merged turn keeps what the access policy reads from its messages.

A group shares one gate key (the chat), but the router takes the identity of a turn from the first message of the merged
one: text of several senders merged into a single turn would run as its first sender, a stranger's words under the
owner's tools. A merged message is also built by hand, so a sender-level flag it does not carry over is lost: the policy
then reads a bot as a person, and the order of the messages decides whether an explicit mention counts. The host here
only runs each turn: the gate ends it when the callback returns.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.protocols.pairing import ChannelPolicyProvider
from app.channels.routing.policy_resolver_support import check_guest_mention_allowed, should_respond_in_group_support
from app.channels.routing.session_gate import SessionGate, SessionGateConfig, merge_messages
from app.channels.types import METADATA_EXPLICIT_MENTION_KEY, InboundMessage

_ANSWER: dict[str, object] = {"decisions": [{"type": "approve"}]}


def _group(sender: str, content: str, *, is_bot: bool = False, metadata: dict[str, object] | None = None) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id=sender,
        chat_id="g1",
        is_group=True,
        content=content,
        is_bot=is_bot,
        metadata=metadata or {},
    )


def _dm(sender: str, content: str) -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id=sender, chat_id=sender, content=content)


class _Router:
    """What the router does with the gate: runs each turn it is handed."""

    def __init__(self, turn: Callable[[InboundMessage], Awaitable[None]] | None = None) -> None:
        self.turns: list[InboundMessage] = []
        self.running = 0
        self.most_running = 0
        self.gate = SessionGate(SessionGateConfig(debounce_window_ms=30, max_pending_per_session=10), on_ready=self._run)
        self._turn = turn

    async def _run(self, msg: InboundMessage) -> None:
        self.turns.append(msg)
        self.running += 1
        self.most_running = max(self.most_running, self.running)
        try:
            if self._turn is not None:
                await self._turn(msg)
        finally:
            self.running -= 1

    def ran(self) -> list[tuple[str, str]]:
        """What ran, in order: (sender, merged text)."""
        return [(t.sender_id, t.content) for t in self.turns]


async def _settle() -> None:
    await asyncio.sleep(0.25)


def _holding_first_turn() -> tuple[asyncio.Event, Callable[[InboundMessage], Awaitable[None]]]:
    """A turn that keeps the session busy until the event is set, so later messages queue behind it."""
    release = asyncio.Event()

    async def turn(msg: InboundMessage) -> None:
        if msg.content == "first":
            await release.wait()

    return release, turn


class TestOneTurnOneSender:
    @pytest.mark.parametrize("first_sender", ["li", "wang"])
    async def test_senders_of_one_debounce_window_get_a_turn_each(self, first_sender: str) -> None:
        other = "wang" if first_sender == "li" else "li"
        router = _Router()

        router.gate.submit(_group(first_sender, "a"))
        router.gate.submit(_group(other, "b"))
        await _settle()

        assert router.ran() == [(first_sender, "a"), (other, "b")]

    async def test_text_queued_behind_a_running_turn_is_split_by_sender(self) -> None:
        release, turn = _holding_first_turn()
        router = _Router(turn)
        router.gate.submit(_group("li", "first"))
        await _settle()

        for sender, text in (("li", "a"), ("li", "b"), ("wang", "c"), ("wang", "d")):
            router.gate.submit(_group(sender, text))
        release.set()
        await _settle()

        assert router.ran() == [("li", "first"), ("li", "a\nb"), ("wang", "c\nd")]

    async def test_interleaved_senders_keep_their_arrival_order(self) -> None:
        release, turn = _holding_first_turn()
        router = _Router(turn)
        router.gate.submit(_group("li", "first"))
        await _settle()

        for sender, text in (("li", "a"), ("wang", "b"), ("li", "c")):
            router.gate.submit(_group(sender, text))
        release.set()
        await _settle()

        assert router.ran() == [("li", "first"), ("li", "a"), ("wang", "b"), ("li", "c")]

    @pytest.mark.parametrize("build", [_group, _dm], ids=["group", "dm"])
    async def test_one_senders_consecutive_messages_still_merge(self, build: Callable[[str, str], InboundMessage]) -> None:
        router = _Router()

        for text in ("a", "b", "c"):
            router.gate.submit(build("li", text))
        await _settle()

        assert router.ran() == [("li", "a\nb\nc")]

    async def test_turns_of_different_senders_never_overlap(self) -> None:
        async def takes_a_while(_: InboundMessage) -> None:
            await asyncio.sleep(0.05)

        router = _Router(takes_a_while)

        for sender, text in (("li", "a"), ("wang", "b"), ("zhao", "c")):
            router.gate.submit(_group(sender, text))
        await asyncio.sleep(0.6)

        assert router.ran() == [("li", "a"), ("wang", "b"), ("zhao", "c")]
        assert router.most_running == 1

    async def test_an_answer_still_runs_first_and_alone_beside_text_of_several_senders(self) -> None:
        release, turn = _holding_first_turn()
        router = _Router(turn)
        router.gate.submit(_group("li", "first"))
        await _settle()

        router.gate.submit(_group("wang", "b"))
        router.gate.submit(
            InboundMessage(channel="telegram", sender_id="li", chat_id="g1", is_group=True, content="", resume_value=_ANSWER)
        )
        router.gate.submit(_group("li", "a"))
        release.set()
        await _settle()

        assert [t.resume_value is not None for t in router.turns] == [False, True, False, False]
        assert router.ran()[2:] == [("wang", "b"), ("li", "a")]


class TestMergedMessageKeepsWhatThePolicyReads:
    @pytest.mark.parametrize("explicit_first", [True, False], ids=["explicit-first", "explicit-last"])
    async def test_an_explicit_mention_survives_the_merge_in_either_order(self, explicit_first: bool) -> None:
        explicit = _group("li", "@bot hi", metadata={METADATA_EXPLICIT_MENTION_KEY: "1"})
        reply = _group("li", "and also this", metadata={"reply": "1"})

        merged = merge_messages((explicit, reply) if explicit_first else (reply, explicit))

        policy = MagicMock(spec=ChannelPolicyProvider)
        policy.get_guest_mode = AsyncMock(return_value=True)
        assert merged.metadata[METADATA_EXPLICIT_MENTION_KEY] == "1"
        assert await check_guest_mention_allowed(policy, merged) is True

    async def test_without_an_explicit_mention_the_merged_message_has_none(self) -> None:
        merged = merge_messages((_group("li", "a"), _group("li", "b")))

        policy = MagicMock(spec=ChannelPolicyProvider)
        policy.get_guest_mode = AsyncMock(return_value=True)
        assert METADATA_EXPLICIT_MENTION_KEY not in merged.metadata
        assert await check_guest_mention_allowed(policy, merged) is False

    async def test_the_last_message_still_provides_the_rest_of_the_metadata(self) -> None:
        merged = merge_messages(
            (
                _group("li", "a", metadata={"locale": "en", METADATA_EXPLICIT_MENTION_KEY: "1"}),
                _group("li", "b", metadata={"locale": "zh"}),
            )
        )

        assert merged.metadata == {"locale": "zh", METADATA_EXPLICIT_MENTION_KEY: "1"}

    async def test_a_bot_stays_a_bot_after_the_merge(self) -> None:
        merged = merge_messages((_group("alertbot", "disk 91%", is_bot=True), _group("alertbot", "disk 93%", is_bot=True)))

        responds, _ = await should_respond_in_group_support(None, MagicMock(), MagicMock(), merged)

        assert merged.is_bot is True
        assert responds is False

    async def test_a_person_stays_a_person_after_the_merge(self) -> None:
        merged = merge_messages((_group("li", "a"), _group("li", "b")))

        assert merged.is_bot is False
