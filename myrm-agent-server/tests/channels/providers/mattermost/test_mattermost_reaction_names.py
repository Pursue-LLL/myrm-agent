"""Mattermost's reactions API takes a short name, so the glyphs the router sends must reach it as names."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.channels.routing.router_models import ReactionPolicy
from tests.channels.providers.mattermost.test_mattermost_channel import _make_channel


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("emoji", "name"),
    [
        (ReactionPolicy().processing_emoji, "eyes"),
        (ReactionPolicy().completion_emoji, "white_check_mark"),
        (ReactionPolicy().failure_emoji, "x"),
    ],
)
async def test_the_routers_default_reactions_reach_mattermost_as_short_names(emoji: str, name: str) -> None:
    ch = _make_channel()

    with patch.object(ch._api, "add_reaction", new_callable=AsyncMock) as add:
        await ch.react_to_message("ch_1", "post_1", emoji)

    add.assert_called_once_with("bot_user_id", "post_1", name)
