"""Matrix reacts with an annotation event and takes the reaction back by redacting that event.

The fake client keeps the room state the Matrix client-server API enforces: a reaction is an ``m.annotation`` event on an
existing event, a sender cannot annotate the same event with the same key twice (``M_DUPLICATE_ANNOTATION``), and
redaction applies to the reaction's own event, never to the message it targets.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

import pytest

from app.channels.providers.matrix import MatrixChannel
from app.channels.providers.matrix.channel import _MAUTRIX_AVAILABLE

pytestmark = pytest.mark.skipif(not _MAUTRIX_AVAILABLE, reason="mautrix not installed")

ROOM = "!room:example.com"
MESSAGE = "$message"
EYES = "\U0001f440"
CHECK = "\u2705"


class _Content(Protocol):
    def serialize(self) -> dict[str, dict[str, str]]: ...


class _FakeRoomClient:
    """The slice of the mautrix client a reaction uses, with the room rules of the Matrix client-server API."""

    def __init__(self) -> None:
        self.events = {MESSAGE}
        self.annotations: dict[str, tuple[str, str]] = {}
        self.redacted: list[str] = []

    async def send_message_event(self, room_id: str, event_type: object, content: _Content) -> str:
        relation = content.serialize()["m.relates_to"]
        if str(event_type) != "m.reaction" or relation["rel_type"] != "m.annotation" or not relation["key"]:
            raise RuntimeError("M_BAD_JSON")
        if relation["event_id"] not in self.events:
            raise RuntimeError("M_NOT_FOUND")
        if (relation["event_id"], relation["key"]) in self.annotations.values():
            raise RuntimeError("M_DUPLICATE_ANNOTATION")
        event_id = f"$reaction{len(self.events)}"
        self.events.add(event_id)
        self.annotations[event_id] = (relation["event_id"], relation["key"])
        return event_id

    async def redact(self, room_id: str, event_id: str, reason: str | None = None) -> str:
        if event_id not in self.annotations:
            raise RuntimeError("M_NOT_FOUND")
        del self.annotations[event_id]
        self.redacted.append(event_id)
        return "$redaction"


def _channel() -> tuple[MatrixChannel, _FakeRoomClient]:
    ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
    client = _FakeRoomClient()
    ch._client = client  # type: ignore[assignment]
    return ch, client


class TestReactToMessage:
    @pytest.mark.asyncio
    async def test_a_reaction_annotates_the_message_with_the_emoji(self) -> None:
        ch, client = _channel()
        await ch.react_to_message(ROOM, MESSAGE, EYES)
        assert list(client.annotations.values()) == [(MESSAGE, EYES)]

    @pytest.mark.asyncio
    async def test_an_empty_emoji_redacts_the_reaction_event_not_the_message(self) -> None:
        ch, client = _channel()
        await ch.react_to_message(ROOM, MESSAGE, EYES)
        reaction_id = next(iter(client.annotations))
        await ch.react_to_message(ROOM, MESSAGE, "")
        assert client.redacted == [reaction_id]
        assert client.annotations == {}
        assert MESSAGE in client.events

    @pytest.mark.asyncio
    async def test_an_empty_emoji_sends_nothing_when_nothing_was_added(self) -> None:
        ch, client = _channel()
        await ch.react_to_message(ROOM, MESSAGE, "")
        assert client.redacted == []

    @pytest.mark.asyncio
    async def test_a_reaction_is_redacted_only_once(self) -> None:
        ch, client = _channel()
        await ch.react_to_message(ROOM, MESSAGE, CHECK)
        await ch.react_to_message(ROOM, MESSAGE, "")
        await ch.react_to_message(ROOM, MESSAGE, "")
        assert len(client.redacted) == 1

    @pytest.mark.asyncio
    async def test_the_same_key_can_be_added_again_after_it_was_redacted(self) -> None:
        ch, client = _channel()
        await ch.react_to_message(ROOM, MESSAGE, EYES)
        await ch.react_to_message(ROOM, MESSAGE, "")
        await ch.react_to_message(ROOM, MESSAGE, EYES)
        assert list(client.annotations.values()) == [(MESSAGE, EYES)]

    @pytest.mark.asyncio
    async def test_without_a_client_nothing_happens(self) -> None:
        ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok")
        await ch.react_to_message(ROOM, MESSAGE, EYES)
        await ch.react_to_message(ROOM, MESSAGE, "")


class TestFailures:
    @pytest.mark.asyncio
    async def test_a_refused_reaction_raises_and_is_not_remembered(self) -> None:
        ch, client = _channel()
        with pytest.raises(RuntimeError, match="M_NOT_FOUND"):
            await ch.react_to_message(ROOM, "$unknown", EYES)
        await ch.react_to_message(ROOM, "$unknown", "")
        assert client.redacted == []

    @pytest.mark.asyncio
    async def test_a_duplicate_reaction_raises_instead_of_being_swallowed(self) -> None:
        ch, _ = _channel()
        await ch.react_to_message(ROOM, MESSAGE, EYES)
        with pytest.raises(RuntimeError, match="M_DUPLICATE_ANNOTATION"):
            await ch.react_to_message(ROOM, MESSAGE, EYES)

    @pytest.mark.asyncio
    async def test_a_failed_redaction_raises(self) -> None:
        ch, client = _channel()
        await ch.react_to_message(ROOM, MESSAGE, EYES)
        client.annotations.clear()
        with pytest.raises(RuntimeError, match="M_NOT_FOUND"):
            await ch.react_to_message(ROOM, MESSAGE, "")

    @pytest.mark.asyncio
    async def test_a_homeserver_that_never_answers_times_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ch, client = _channel()

        async def hang(*_: object) -> str:
            await asyncio.sleep(60)
            return "$never"

        client.send_message_event = hang  # type: ignore[method-assign,assignment]
        monkeypatch.setattr("app.channels.providers.matrix.channel._REACTION_TIMEOUT", 0.01)
        with pytest.raises(asyncio.TimeoutError):
            await ch.react_to_message(ROOM, MESSAGE, EYES)
