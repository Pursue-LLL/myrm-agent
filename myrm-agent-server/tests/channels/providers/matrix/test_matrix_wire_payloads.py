"""What a Matrix room receives from the channel: the event type and JSON content of each text send and edit.

The channel hands plain dicts to the mautrix client (which serialises a non-``Serializable`` content as it is), so the
JSON a homeserver sees is exactly what these tests pin: a plain or HTML-formatted ``m.text`` event, a reply relation, an
edit that carries the new content, one retry after sharing E2EE keys, and a send that is cut short at the timeout.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.matrix import MatrixChannel
from app.channels.providers.matrix import channel as matrix_channel
from app.channels.providers.matrix.channel import _MAUTRIX_AVAILABLE
from app.channels.types import ChannelStatus, OutboundMessage

pytestmark = pytest.mark.skipif(not _MAUTRIX_AVAILABLE, reason="mautrix not installed")

ROOM = "!room:example.com"
HTML = "org.matrix.custom.html"


@dataclass
class _Crypto:
    shared: int = 0

    async def share_keys(self) -> None:
        self.shared += 1


@dataclass
class _Homeserver:
    """The slice of the mautrix client a text send or edit uses; records the room events it was asked to create."""

    refusals: int = 0
    never_answers: bool = False
    events: list[tuple[str, str, dict[str, object]]] = field(default_factory=list)
    crypto: _Crypto = field(default_factory=_Crypto)

    async def send_message_event(self, room_id: str, event_type: object, content: dict[str, object]) -> str:
        if self.never_answers:
            await asyncio.Event().wait()
        if self.refusals:
            self.refusals -= 1
            raise RuntimeError("M_UNKNOWN: session expired")
        self.events.append((str(room_id), str(event_type), content))
        return f"$event{len(self.events)}"

    async def get_joined_members(self, room_id: str) -> dict[str, object]:
        return {}


def _channel(homeserver: _Homeserver, *, encryption: bool = False) -> MatrixChannel:
    ch = MatrixChannel(homeserver="https://matrix.example.com", access_token="tok", encryption=str(encryption).lower())
    ch._status = ChannelStatus.RUNNING
    ch._client = homeserver  # type: ignore[assignment]
    return ch


def _message(content: str, *, reply_to: str | None = None) -> OutboundMessage:
    return OutboundMessage(channel="matrix", recipient_id=ROOM, content=content, user_id="@u:example.com", reply_to_id=reply_to)


class TestTextSend:
    @pytest.mark.asyncio
    async def test_plain_text_is_an_m_text_event(self) -> None:
        server = _Homeserver()
        assert await _channel(server).send(_message("hello")) == "$event1"
        assert server.events == [(ROOM, "m.room.message", {"msgtype": "m.text", "body": "hello"})]

    @pytest.mark.asyncio
    async def test_markdown_is_sent_with_its_html_form(self) -> None:
        server = _Homeserver()
        await _channel(server).send(_message("**done**"))
        assert server.events == [
            (
                ROOM,
                "m.room.message",
                {"msgtype": "m.text", "body": "**done**", "format": HTML, "formatted_body": "<strong>done</strong>"},
            )
        ]

    @pytest.mark.asyncio
    async def test_a_reply_names_the_event_it_answers(self) -> None:
        server = _Homeserver()
        await _channel(server).send(_message("ok", reply_to="$question"))
        assert server.events[0][2] == {
            "msgtype": "m.text",
            "body": "ok",
            "m.relates_to": {"m.in_reply_to": {"event_id": "$question"}},
        }

    @pytest.mark.asyncio
    async def test_a_refused_send_is_retried_once_after_the_room_keys_are_shared(self) -> None:
        server = _Homeserver(refusals=1)
        assert await _channel(server, encryption=True).send(_message("hello")) == "$event1"
        assert server.crypto.shared == 1
        assert server.events == [(ROOM, "m.room.message", {"msgtype": "m.text", "body": "hello"})]

    @pytest.mark.asyncio
    async def test_a_send_refused_again_after_sharing_keys_is_a_failed_send(self) -> None:
        server = _Homeserver(refusals=2)
        with pytest.raises(ChannelSendError, match="after key share retry"):
            await _channel(server, encryption=True).send(_message("hello"))
        assert server.events == []

    @pytest.mark.asyncio
    async def test_a_refused_send_without_encryption_is_not_retried(self) -> None:
        server = _Homeserver(refusals=1)
        with pytest.raises(ChannelSendError, match="session expired"):
            await _channel(server).send(_message("hello"))
        assert server.crypto.shared == 0

    @pytest.mark.asyncio
    async def test_a_homeserver_that_never_answers_fails_the_send_at_the_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(matrix_channel, "_SEND_TIMEOUT", 0.05)
        with pytest.raises(ChannelSendError, match="Matrix send failed"):
            await _channel(_Homeserver(never_answers=True)).send(_message("hello"))


class TestEdit:
    @pytest.mark.asyncio
    async def test_an_edit_replaces_the_event_and_carries_the_new_content(self) -> None:
        server = _Homeserver()
        await _channel(server).edit_message(ROOM, "$old", "**fixed**")
        assert server.events == [
            (
                ROOM,
                "m.room.message",
                {
                    "msgtype": "m.text",
                    "body": "* **fixed**",
                    "m.new_content": {
                        "msgtype": "m.text",
                        "body": "**fixed**",
                        "format": HTML,
                        "formatted_body": "<strong>fixed</strong>",
                    },
                    "m.relates_to": {"rel_type": "m.replace", "event_id": "$old"},
                },
            )
        ]

    @pytest.mark.asyncio
    async def test_a_refused_edit_never_reaches_the_caller(self) -> None:
        await _channel(_Homeserver(refusals=1)).edit_message(ROOM, "$old", "fixed")

    @pytest.mark.asyncio
    async def test_a_homeserver_that_never_answers_does_not_hold_an_edit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(matrix_channel, "_SEND_TIMEOUT", 0.05)
        await _channel(_Homeserver(never_answers=True)).edit_message(ROOM, "$old", "fixed")
