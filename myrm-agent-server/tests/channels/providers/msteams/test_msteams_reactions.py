"""Teams has six reaction types; a glyph without a faithful type is skipped, never sent as a thumbs-up.

The old map answered every unknown glyph (and the cross, the eyes, the check mark, the thinking
face) with ``like``, so a failed turn showed a thumbs-up.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.channels.providers.msteams import MSTeamsChannel

THUMBS_UP = "\U0001f44d"


def _channel() -> MSTeamsChannel:
    ch = MSTeamsChannel(app_id="test_app_id", app_password="test_app_password")
    ch._api.add_reaction = AsyncMock()
    ch._api.resolve_service_url = lambda _chat_id: "https://svc.url"  # type: ignore[method-assign]
    return ch


class TestDeclaredVocabulary:
    @pytest.mark.parametrize("glyph", [THUMBS_UP, "\u2764\ufe0f", "\U0001f602", "\U0001f62e", "\U0001f622", "\U0001f620"])
    def test_accepts_the_six_native_types(self, glyph: str) -> None:
        assert MSTeamsChannel.capabilities.accepts_reaction(glyph)

    @pytest.mark.parametrize("glyph", ["\U0001f440", "\u2705", "\u274c", "\U0001f44e", "\U0001f914"])
    def test_rejects_glyphs_that_have_no_faithful_type(self, glyph: str) -> None:
        assert not MSTeamsChannel.capabilities.accepts_reaction(glyph)


class TestReactToMessage:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("glyph", "reaction_type"),
        [(THUMBS_UP, "like"), ("\u2764", "heart"), ("\u2764\ufe0f", "heart"), ("\U0001f622", "sad"), ("\U0001f620", "angry")],
    )
    async def test_a_glyph_is_sent_as_its_own_type(self, glyph: str, reaction_type: str) -> None:
        ch = _channel()
        await ch.react_to_message("conv", "act1", glyph)
        ch._api.add_reaction.assert_awaited_once_with("https://svc.url", "conv", "act1", reaction_type)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("glyph", ["\u274c", "\U0001f440", "\U0001f44e"])
    async def test_a_glyph_without_a_type_sends_nothing(self, glyph: str) -> None:
        ch = _channel()
        await ch.react_to_message("conv", "act1", glyph)
        ch._api.add_reaction.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_request_reaches_the_caller(self) -> None:
        ch = _channel()
        ch._api.add_reaction.side_effect = ConnectionError("down")
        with pytest.raises(ConnectionError):
            await ch.react_to_message("conv", "act1", THUMBS_UP)
