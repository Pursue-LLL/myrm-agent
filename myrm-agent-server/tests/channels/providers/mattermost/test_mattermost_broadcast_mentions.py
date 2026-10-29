"""Text the agent writes cannot notify a whole Mattermost channel.

Mattermost notifies every member of a channel for ``@channel``, ``@all`` and ``@here`` anywhere in the text of a
post, so the words are broken up in everything the bot posts or edits: replies, placeholders and progress edits.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.providers.mattermost import MattermostChannel
from app.channels.providers.mattermost.api import MattermostClient, neutralize_broadcast_mentions
from app.channels.types import OutboundMessage

_ZWSP = "\u200b"
_NOTIFIES = re.compile(r"(?<!\w)@(?:channel|all|here)\b", re.IGNORECASE)
_BROADCASTS = ["@channel", "@all", "@here", "@CHANNEL", "@Here"]
_CONTEXTS = [
    "{}",
    "Heads up {} please read",
    "({})",
    "line one\n{}\nline three",
    "```\n{}\n```",
    "{}, then {}!",
]


@pytest.mark.parametrize("template", _CONTEXTS)
@pytest.mark.parametrize("word", _BROADCASTS)
def test_a_broadcast_mention_no_longer_notifies(word: str, template: str) -> None:
    text = template.format(*([word] * template.count("{}")))

    neutral = neutralize_broadcast_mentions(text)

    assert _NOTIFIES.search(text)
    assert not _NOTIFIES.search(neutral)
    assert neutral.replace(_ZWSP, "") == text


@pytest.mark.parametrize(
    "text",
    ["mail bob@here.com", "ping @alice", "@channels", "@allison", "@here_team", "user@all", "no mention at all", ""],
)
def test_text_that_does_not_notify_a_channel_is_left_as_it_is(text: str) -> None:
    assert neutralize_broadcast_mentions(text) == text


def test_neutralizing_twice_changes_nothing() -> None:
    once = neutralize_broadcast_mentions("@here and @all and @channel")

    assert neutralize_broadcast_mentions(once) == once


def _http() -> MagicMock:
    reply = httpx.Response(200, json={"id": "p1"}, request=httpx.Request("POST", "https://mm.example.com"))
    http = MagicMock()
    http.post = AsyncMock(return_value=reply)
    http.put = AsyncMock(return_value=reply)
    return http


class TestWhatReachesMattermost:
    @pytest.mark.asyncio
    async def test_a_created_post(self) -> None:
        client, http = MattermostClient("https://mm.example.com", "t"), _http()

        with patch.object(client, "_get_http", return_value=http):
            await client.create_post("c1", "Hi @channel", root_id="r1")

        assert http.post.await_args.kwargs["json"]["message"] == f"Hi @{_ZWSP}channel"

    @pytest.mark.asyncio
    async def test_an_edited_post(self) -> None:
        client, http = MattermostClient("https://mm.example.com", "t"), _http()

        with patch.object(client, "_get_http", return_value=http):
            await client.update_post("p1", "now @here")

        assert http.put.await_args.kwargs["json"]["message"] == f"now @{_ZWSP}here"


class TestEveryOutboundPath:
    @staticmethod
    def _channel() -> MattermostChannel:
        return MattermostChannel(server_url="https://mm.example.com", access_token="t")

    @pytest.mark.asyncio
    async def test_a_reply(self) -> None:
        channel, http = self._channel(), _http()
        reply = OutboundMessage(channel="mattermost", recipient_id="c1", content="Done @all", user_id="u")

        with patch.object(channel._api, "_get_http", return_value=http):
            await channel.send(reply)

        assert http.post.await_args.kwargs["json"]["message"] == f"Done @{_ZWSP}all"

    @pytest.mark.asyncio
    async def test_a_placeholder(self) -> None:
        channel, http = self._channel(), _http()

        with patch.object(channel._api, "_get_http", return_value=http):
            await channel.send_placeholder("c1", "Looking at @channel")

        assert http.post.await_args.kwargs["json"]["message"] == f"Looking at @{_ZWSP}channel"

    @pytest.mark.asyncio
    async def test_a_progress_edit_and_the_final_reply_that_replaces_the_placeholder(self) -> None:
        channel, http = self._channel(), _http()
        final = OutboundMessage(channel="mattermost", recipient_id="c1", content="Done @here", user_id="u")

        with patch.object(channel._api, "_get_http", return_value=http):
            await channel.edit_message("c1", "p1", "step @all")
            await channel.edit_placeholder_message("c1", "p1", final)

        edited = [call.kwargs["json"]["message"] for call in http.put.await_args_list]
        assert edited == [f"step @{_ZWSP}all", f"Done @{_ZWSP}here"]
