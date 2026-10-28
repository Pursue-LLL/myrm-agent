"""iMessage reacts through BlueBubbles' ``/api/v1/message/react``, which takes one of six Tapback names.

The fake server enforces the validator of bluebubbles-server (``MessageValidator.sendReactionRules``: ``reaction`` is
a string in ``MessageInterface.possibleReactions``, the six names and each behind ``-`` to remove it), so a payload
the real server would refuse fails here too. A glyph without a Tapback is never sent as a thumbs-up, and a removal
takes down the Tapback this channel sent, never one the user set.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.imessage import IMessageChannel

THUMBS_UP = "\U0001f44d"
HEART = "\u2764"
EYES = "\U0001f440"

_TAPBACK_NAMES = ("love", "like", "dislike", "laugh", "emphasize", "question")
_ACCEPTED = frozenset((*_TAPBACK_NAMES, *(f"-{name}" for name in _TAPBACK_NAMES)))
_PASSWORD = "test_pass"


class _FakeBlueBubbles:
    """Records every reaction request and answers like the real validator."""

    def __init__(self) -> None:
        self.reactions: list[object] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        reaction = body.get("reaction")
        self.reactions.append(reaction)
        accepted = (
            request.url.path == "/api/v1/message/react"
            and request.url.params.get("password") == _PASSWORD
            and isinstance(reaction, str)
            and reaction in _ACCEPTED
            and bool(body.get("chatGuid"))
            and bool(body.get("selectedMessageGuid"))
        )
        return httpx.Response(200 if accepted else 400, json={})


def _channel(handler: httpx.MockTransport | None = None) -> tuple[IMessageChannel, _FakeBlueBubbles]:
    server = _FakeBlueBubbles()
    ch = IMessageChannel(api_url="http://localhost:1234", password=_PASSWORD)
    ch._http = httpx.AsyncClient(transport=handler or httpx.MockTransport(server.handle))
    return ch, server


class TestDeclaredVocabulary:
    @pytest.mark.parametrize(
        "glyph", [THUMBS_UP, "\U0001f44e", HEART, "\u2764\ufe0f", "\U0001f602", "\u2757", "\u203c\ufe0f", "\u2753"]
    )
    def test_accepts_the_six_tapbacks(self, glyph: str) -> None:
        assert IMessageChannel.capabilities.accepts_reaction(glyph)

    @pytest.mark.parametrize("glyph", [EYES, "\u2705", "\u274c", "\U0001f914"])
    def test_rejects_glyphs_that_are_not_a_tapback(self, glyph: str) -> None:
        assert not IMessageChannel.capabilities.accepts_reaction(glyph)

    @pytest.mark.asyncio
    async def test_every_declared_glyph_passes_the_server_validation(self) -> None:
        ch, server = _channel()
        for glyph in IMessageChannel.capabilities.reaction_glyphs:
            await ch.react_to_message("chat1", "msg1", glyph)
            await ch.react_to_message("chat1", "msg1", "")
        assert server.reactions
        assert all(reaction in _ACCEPTED for reaction in server.reactions)


class TestReactToMessage:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("glyph", "name"),
        [(THUMBS_UP, "like"), (HEART, "love"), ("\u2764\ufe0f", "love"), ("\u203c\ufe0f", "emphasize"), ("\u2753", "question")],
    )
    async def test_a_glyph_is_sent_as_its_tapback_name(self, glyph: str, name: str) -> None:
        ch, server = _channel()
        await ch.react_to_message("chat1", "msg1", glyph)
        assert server.reactions == [name]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("glyph", [EYES, "\U0001f525"])
    async def test_a_glyph_that_is_not_a_tapback_sends_nothing(self, glyph: str) -> None:
        ch, server = _channel()
        await ch.react_to_message("chat1", "msg1", glyph)
        assert server.reactions == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("glyph", "removal"), [(THUMBS_UP, "-like"), (HEART, "-love"), ("\U0001f44e", "-dislike")])
    async def test_an_empty_emoji_removes_the_tapback_that_was_sent(self, glyph: str, removal: str) -> None:
        ch, server = _channel()
        await ch.react_to_message("chat1", "msg1", glyph)
        await ch.react_to_message("chat1", "msg1", "")
        assert server.reactions[1] == removal

    @pytest.mark.asyncio
    async def test_an_empty_emoji_sends_nothing_when_no_tapback_was_sent(self) -> None:
        ch, server = _channel()
        await ch.react_to_message("chat1", "msg1", "")
        assert server.reactions == []

    @pytest.mark.asyncio
    async def test_a_tapback_is_removed_only_once(self) -> None:
        ch, server = _channel()
        await ch.react_to_message("chat1", "msg1", THUMBS_UP)
        await ch.react_to_message("chat1", "msg1", "")
        await ch.react_to_message("chat1", "msg1", "")
        assert server.reactions == ["like", "-like"]

    @pytest.mark.asyncio
    async def test_a_rejected_tapback_raises_and_is_not_remembered(self) -> None:
        requests: list[httpx.Request] = []

        def refuse(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(500, json={})

        ch, _ = _channel(httpx.MockTransport(refuse))
        with pytest.raises(ChannelSendError, match="HTTP 500"):
            await ch.react_to_message("chat1", "msg1", THUMBS_UP)
        await ch.react_to_message("chat1", "msg1", "")
        assert len(requests) == 1

    @pytest.mark.asyncio
    async def test_a_transport_error_propagates(self) -> None:
        def unreachable(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("net", request=request)

        ch, _ = _channel(httpx.MockTransport(unreachable))
        with pytest.raises(httpx.ConnectError):
            await ch.react_to_message("chat1", "msg1", THUMBS_UP)
