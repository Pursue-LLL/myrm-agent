"""Mattermost removes the bot's own reaction through ``DELETE /users/{id}/posts/{id}/reactions/{name}``."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.providers.mattermost.api import MattermostClient
from tests.channels.providers.mattermost.test_mattermost_channel import _make_channel

EYES = "\U0001f440"


@pytest.mark.asyncio
async def test_an_empty_emoji_removes_the_reaction_that_was_added() -> None:
    ch = _make_channel()
    with (
        patch.object(ch._api, "add_reaction", new_callable=AsyncMock),
        patch.object(ch._api, "remove_reaction", new_callable=AsyncMock) as remove,
    ):
        await ch.react_to_message("ch_1", "post_1", EYES)
        await ch.react_to_message("ch_1", "post_1", "")
        await ch.react_to_message("ch_1", "post_1", "")

    remove.assert_awaited_once_with("bot_user_id", "post_1", "eyes")


@pytest.mark.asyncio
async def test_an_empty_emoji_calls_nothing_when_no_reaction_was_added() -> None:
    ch = _make_channel()
    with patch.object(ch._api, "remove_reaction", new_callable=AsyncMock) as remove:
        await ch.react_to_message("ch_1", "post_1", "")
    remove.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_add_raises_and_is_not_remembered() -> None:
    ch = _make_channel()
    with (
        patch.object(ch._api, "add_reaction", new_callable=AsyncMock, side_effect=RuntimeError("403")),
        patch.object(ch._api, "remove_reaction", new_callable=AsyncMock) as remove,
    ):
        with pytest.raises(RuntimeError, match="403"):
            await ch.react_to_message("ch_1", "post_1", EYES)
        await ch.react_to_message("ch_1", "post_1", "")
    remove.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_client_deletes_the_reaction_by_user_post_and_name() -> None:
    client = MattermostClient("https://mm.example.com", "token")
    http = MagicMock(is_closed=False, delete=AsyncMock(return_value=MagicMock(raise_for_status=MagicMock())))
    client._http = http

    await client.remove_reaction("user_1", "post_1", "eyes")

    http.delete.assert_awaited_once_with("https://mm.example.com/api/v4/users/user_1/posts/post_1/reactions/eyes")
