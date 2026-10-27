"""Slack's ``reactions.add`` takes a short name, so the glyphs the router sends must reach it as names."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.channels.routing.router_models import ReactionPolicy
from tests.channels.providers.slack.test_slack_channel import _make_channel, _ok_json


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("emoji", "name"),
    [
        (ReactionPolicy().processing_emoji, "eyes"),
        (ReactionPolicy().completion_emoji, "white_check_mark"),
        (ReactionPolicy().failure_emoji, "x"),
    ],
)
async def test_the_routers_default_reactions_reach_slack_as_short_names(emoji: str, name: str) -> None:
    ch = _make_channel()

    with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=_ok_json()) as post:
        await ch.react_to_message("C1", "1700000000.000100", emoji)

    assert post.call_args.kwargs["json"] == {"channel": "C1", "timestamp": "1700000000.000100", "name": name}
