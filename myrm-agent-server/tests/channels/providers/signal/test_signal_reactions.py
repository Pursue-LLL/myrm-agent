"""Signal reacts through signal-cli-rest-api with a flat ``reaction`` string, and addresses groups as the wrapper requires.

The fake wrapper enforces the rules of bbernhard/signal-cli-rest-api: ``POST``/``DELETE /v1/reactions/{number}`` need a
string ``reaction`` (``POST`` only), a ``recipient``, a ``target_author`` and a non-zero ``timestamp`` (``src/api/api.go``
``SendReaction``/``RemoveReaction``), and a recipient is a number, a UUID or ``group.`` + base64 of the group's bare id
(``src/client/client.go`` ``getRecipientType``); any other string is read as a username, which never reaches a group.
"""

from __future__ import annotations

import base64
import json
import re
import uuid

import httpx
import pytest

from app.channels.core.allow_policy import AllowPolicy, ChatPolicy
from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.signal import SignalChannel
from app.channels.providers.signal.addressing import MessageAuthors, is_group_id, wire_recipient
from app.channels.types import InboundMessage, OutboundMessage

NUMBER = "+1234567890"
USER = "+9999999999"
OTHER_USER = "+8888888888"
GROUP_ID = base64.b64encode(bytes(range(32))).decode()
GROUP_RECIPIENT = "group." + base64.b64encode(GROUP_ID.encode()).decode()
EYES = "\U0001f440"
CHECK = "\u2705"


def _valid_recipient(recipient: object) -> bool:
    if not isinstance(recipient, str):
        return False
    if recipient.startswith("group."):
        try:
            return len(base64.b64decode(base64.b64decode(recipient.removeprefix("group.")), validate=True)) == 32
        except ValueError:
            return False
    if re.fullmatch(r"\+[1-9]\d{6,14}", recipient):
        return True
    try:
        uuid.UUID(recipient)
    except ValueError:
        return False
    return True


class _FakeWrapper:
    """Records the reactions and messages signal-cli-rest-api would accept; refuses what it would answer 400 to."""

    def __init__(self, status: int | None = None) -> None:
        self.reactions: list[tuple[str, dict[str, object]]] = []
        self.sent: list[dict[str, object]] = []
        self._status = status

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        if request.url.path == f"/v1/reactions/{NUMBER}" and request.method in {"POST", "DELETE"}:
            return self._reaction(request.method, body)
        if request.url.path == "/v2/send" and request.method == "POST":
            return self._send(body)
        return httpx.Response(404)

    def _reaction(self, method: str, body: dict[str, object]) -> httpx.Response:
        reaction = body.get("reaction")
        accepted = (
            _valid_recipient(body.get("recipient"))
            and isinstance(reaction, str)
            and (method == "DELETE" or reaction != "")
            and bool(body.get("target_author"))
            and isinstance(body.get("timestamp"), int)
            and body["timestamp"] != 0
        )
        if self._status is not None:
            return httpx.Response(self._status, json={"error": "refused"})
        if not accepted:
            return httpx.Response(400, json={"error": "invalid request"})
        self.reactions.append((method, body))
        return httpx.Response(204)

    def _send(self, body: dict[str, object]) -> httpx.Response:
        recipients = body.get("recipients")
        if not isinstance(recipients, list) or not all(_valid_recipient(r) for r in recipients):
            return httpx.Response(400, json={"error": "invalid recipient"})
        self.sent.append(body)
        return httpx.Response(201, json={"timestamp": 1})


def _channel(wrapper: _FakeWrapper | None = None) -> tuple[SignalChannel, _FakeWrapper, list[InboundMessage]]:
    wrapper = wrapper or _FakeWrapper()
    ch = SignalChannel(api_url="http://signal:8080", phone_number=NUMBER)
    ch.allow_policy = AllowPolicy(group_policy=ChatPolicy.ALLOW)
    ch._api._http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper.handle))
    received: list[InboundMessage] = []

    async def _handler(msg: InboundMessage) -> None:
        received.append(msg)

    ch.set_inbound_handler(_handler)
    return ch, wrapper, received


async def _receive_group_message(ch: SignalChannel, *, author: str, timestamp: int) -> None:
    await ch._handle_envelope(
        {
            "envelope": {
                "sourceNumber": author,
                "dataMessage": {"timestamp": timestamp, "message": "hi", "groupInfo": {"groupId": GROUP_ID}},
            }
        }
    )


class TestDirectChat:
    @pytest.mark.asyncio
    async def test_a_reaction_is_a_flat_string_naming_the_chat_as_author(self) -> None:
        ch, wrapper, _ = _channel()
        await ch.react_to_message(USER, "1700", EYES)
        assert wrapper.reactions == [("POST", {"recipient": USER, "reaction": EYES, "target_author": USER, "timestamp": 1700})]

    @pytest.mark.asyncio
    async def test_an_empty_emoji_deletes_the_reaction_that_was_added(self) -> None:
        ch, wrapper, _ = _channel()
        await ch.react_to_message(USER, "1700", EYES)
        await ch.react_to_message(USER, "1700", "")
        assert [(method, body["reaction"]) for method, body in wrapper.reactions] == [("POST", EYES), ("DELETE", EYES)]

    @pytest.mark.asyncio
    async def test_a_replaced_reaction_is_deleted_under_the_latest_emoji(self) -> None:
        ch, wrapper, _ = _channel()
        await ch.react_to_message(USER, "1700", EYES)
        await ch.react_to_message(USER, "1700", CHECK)
        await ch.react_to_message(USER, "1700", "")
        assert wrapper.reactions[-1][1]["reaction"] == CHECK

    @pytest.mark.asyncio
    async def test_an_empty_emoji_sends_nothing_when_nothing_was_added(self) -> None:
        ch, wrapper, _ = _channel()
        await ch.react_to_message(USER, "1700", "")
        assert wrapper.reactions == []

    @pytest.mark.asyncio
    async def test_a_reaction_is_deleted_only_once(self) -> None:
        ch, wrapper, _ = _channel()
        await ch.react_to_message(USER, "1700", EYES)
        await ch.react_to_message(USER, "1700", "")
        await ch.react_to_message(USER, "1700", "")
        assert [method for method, _ in wrapper.reactions] == ["POST", "DELETE"]

    @pytest.mark.asyncio
    async def test_a_message_id_that_is_not_a_timestamp_sends_nothing(self) -> None:
        ch, wrapper, _ = _channel()
        await ch.react_to_message(USER, "not-a-timestamp", EYES)
        assert wrapper.reactions == []


class TestGroupChat:
    @pytest.mark.asyncio
    async def test_a_reaction_names_the_group_and_the_message_author(self) -> None:
        ch, wrapper, _ = _channel()
        await _receive_group_message(ch, author=OTHER_USER, timestamp=555)
        await ch.react_to_message(GROUP_ID, "555", EYES)
        assert wrapper.reactions == [
            ("POST", {"recipient": GROUP_RECIPIENT, "reaction": EYES, "target_author": OTHER_USER, "timestamp": 555})
        ]

    @pytest.mark.asyncio
    async def test_each_message_keeps_its_own_author(self) -> None:
        ch, wrapper, _ = _channel()
        await _receive_group_message(ch, author=USER, timestamp=1)
        await _receive_group_message(ch, author=OTHER_USER, timestamp=2)
        await ch.react_to_message(GROUP_ID, "1", EYES)
        await ch.react_to_message(GROUP_ID, "2", EYES)
        assert [body["target_author"] for _, body in wrapper.reactions] == [USER, OTHER_USER]

    @pytest.mark.asyncio
    async def test_the_reaction_is_deleted_from_the_same_group_message(self) -> None:
        ch, wrapper, _ = _channel()
        await _receive_group_message(ch, author=OTHER_USER, timestamp=555)
        await ch.react_to_message(GROUP_ID, "555", EYES)
        await ch.react_to_message(GROUP_ID, "555", "")
        assert wrapper.reactions[-1] == (
            "DELETE",
            {"recipient": GROUP_RECIPIENT, "reaction": EYES, "target_author": OTHER_USER, "timestamp": 555},
        )

    @pytest.mark.asyncio
    async def test_a_group_message_that_was_never_received_cannot_be_reacted_to(self) -> None:
        ch, wrapper, _ = _channel()
        await ch.react_to_message(GROUP_ID, "555", EYES)
        assert wrapper.reactions == []

    @pytest.mark.asyncio
    async def test_a_reply_to_a_group_is_addressed_in_the_group_form(self) -> None:
        ch, wrapper, _ = _channel()
        await ch.send(OutboundMessage(channel="signal", user_id="u1", recipient_id=GROUP_ID, content="hello"))
        assert wrapper.sent[0]["recipients"] == [GROUP_RECIPIENT]

    @pytest.mark.asyncio
    async def test_a_reply_to_a_direct_chat_is_addressed_by_number(self) -> None:
        ch, wrapper, _ = _channel()
        await ch.send(OutboundMessage(channel="signal", user_id="u1", recipient_id=USER, content="hello"))
        assert wrapper.sent[0]["recipients"] == [USER]


class TestFailures:
    @pytest.mark.asyncio
    async def test_a_refused_reaction_raises_and_is_not_remembered(self) -> None:
        ch, wrapper, _ = _channel(_FakeWrapper(status=400))
        with pytest.raises(ChannelSendError):
            await ch.react_to_message(USER, "1700", EYES)
        await ch.react_to_message(USER, "1700", "")
        assert wrapper.reactions == []

    @pytest.mark.asyncio
    async def test_a_transport_error_surfaces_as_a_send_error(self) -> None:
        ch, _, _ = _channel()

        def unreachable(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("net", request=request)

        ch._api._http = httpx.AsyncClient(transport=httpx.MockTransport(unreachable))
        with pytest.raises(ChannelSendError, match="ConnectError"):
            await ch.react_to_message(USER, "1700", EYES)


class TestAddressing:
    def test_a_bare_group_id_gets_the_group_form(self) -> None:
        assert wire_recipient(GROUP_ID) == GROUP_RECIPIENT

    @pytest.mark.parametrize("chat_id", [USER, "5b4ac8c0-6a7c-4a2b-9f8e-4f4a4c1e2d3b", GROUP_RECIPIENT, "alice.01"])
    def test_everything_else_goes_as_it_is(self, chat_id: str) -> None:
        assert wire_recipient(chat_id) == chat_id

    @pytest.mark.parametrize("chat_id", [USER, "5b4ac8c0-6a7c-4a2b-9f8e-4f4a4c1e2d3b", "", base64.b64encode(bytes(31)).decode()])
    def test_only_32_byte_base64_is_a_group_id(self, chat_id: str) -> None:
        assert not is_group_id(chat_id)

    def test_message_authors_forget_the_oldest_first(self) -> None:
        authors = MessageAuthors(max_entries=2)
        for message_id in ("1", "2", "3"):
            authors.note(GROUP_ID, message_id, USER)
        assert [authors.author_of(GROUP_ID, m) for m in ("1", "2", "3")] == [None, USER, USER]
