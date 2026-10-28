"""iMessage reacts with one of six Tapbacks; anything else is skipped, and an empty emoji removes what was sent.

BlueBubbles removes a Tapback by posting its code plus 1000. The old code answered every unknown
glyph with a thumbs-up and always removed a thumbs-up, so a failed turn showed an approving
Tapback and a removal could take down a Tapback the user had set themselves.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.imessage import IMessageChannel

THUMBS_UP = "\U0001f44d"
HEART = "\u2764"
EYES = "\U0001f440"


def _channel() -> IMessageChannel:
    return IMessageChannel(api_url="http://localhost:1234", password="test_pass")


def _ok() -> httpx.Response:
    return httpx.Response(200, json={})


def _codes(post: AsyncMock) -> list[int]:
    return [call.kwargs["json"]["reaction"] for call in post.await_args_list]


class TestDeclaredVocabulary:
    @pytest.mark.parametrize(
        "glyph", [THUMBS_UP, "\U0001f44e", HEART, "\u2764\ufe0f", "\U0001f602", "\u2757", "\u203c\ufe0f", "\u2753"]
    )
    def test_accepts_the_six_tapbacks(self, glyph: str) -> None:
        assert IMessageChannel.capabilities.accepts_reaction(glyph)

    @pytest.mark.parametrize("glyph", [EYES, "\u2705", "\u274c", "\U0001f914"])
    def test_rejects_glyphs_that_are_not_a_tapback(self, glyph: str) -> None:
        assert not IMessageChannel.capabilities.accepts_reaction(glyph)


class TestReactToMessage:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("glyph", "code"), [(THUMBS_UP, 2001), (HEART, 2000), ("\u2764\ufe0f", 2000), ("\u203c\ufe0f", 2004)]
    )
    async def test_a_glyph_is_sent_as_its_tapback(self, glyph: str, code: int) -> None:
        ch = _channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_ok()) as post:
            await ch.react_to_message("chat1", "msg1", glyph)
        assert _codes(post) == [code]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("glyph", [EYES, "\U0001f525"])
    async def test_a_glyph_that_is_not_a_tapback_sends_nothing(self, glyph: str) -> None:
        ch = _channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_ok()) as post:
            await ch.react_to_message("chat1", "msg1", glyph)
        post.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("glyph", "removal"), [(THUMBS_UP, 3001), (HEART, 3000), ("\U0001f44e", 3002)])
    async def test_an_empty_emoji_removes_the_tapback_that_was_sent(self, glyph: str, removal: int) -> None:
        ch = _channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_ok()) as post:
            await ch.react_to_message("chat1", "msg1", glyph)
            await ch.react_to_message("chat1", "msg1", "")
        assert _codes(post)[1] == removal

    @pytest.mark.asyncio
    async def test_an_empty_emoji_sends_nothing_when_no_tapback_was_sent(self) -> None:
        ch = _channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_ok()) as post:
            await ch.react_to_message("chat1", "msg1", "")
        post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_tapback_is_removed_only_once(self) -> None:
        ch = _channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=_ok()) as post:
            await ch.react_to_message("chat1", "msg1", THUMBS_UP)
            await ch.react_to_message("chat1", "msg1", "")
            await ch.react_to_message("chat1", "msg1", "")
        assert _codes(post) == [2001, 3001]

    @pytest.mark.asyncio
    async def test_a_rejected_tapback_raises_and_is_not_remembered(self) -> None:
        ch = _channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, return_value=httpx.Response(500, json={})) as post:
            with pytest.raises(ChannelSendError, match="HTTP 500"):
                await ch.react_to_message("chat1", "msg1", THUMBS_UP)
            await ch.react_to_message("chat1", "msg1", "")
        assert _codes(post) == [2001]

    @pytest.mark.asyncio
    async def test_a_transport_error_propagates(self) -> None:
        ch = _channel()
        with patch.object(ch._http, "post", new_callable=AsyncMock, side_effect=httpx.ConnectError("net")):
            with pytest.raises(httpx.ConnectError):
                await ch.react_to_message("chat1", "msg1", THUMBS_UP)
