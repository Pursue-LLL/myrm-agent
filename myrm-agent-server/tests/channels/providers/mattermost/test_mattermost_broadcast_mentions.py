"""Text the agent writes cannot notify a whole Mattermost channel.

Mattermost notifies every member of a channel for ``@channel``, ``@all`` and ``@here`` in the text of a post. The
words are broken up in everything the bot posts or edits (replies, placeholders, progress edits), and the check
is made against a port of the server's own word splitter rather than against the rule it is meant to enforce.
"""

from __future__ import annotations

import html
import itertools
import re
import unicodedata
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.providers.mattermost import MattermostChannel
from app.channels.providers.mattermost.api import MattermostClient, neutralize_broadcast_mentions
from app.channels.types import OutboundMessage

_ZWSP = "\u200b"
_SYSTEM_MENTIONS = frozenset({"@here", "@channel", "@all"})


def _is_word_character(char: str) -> bool:
    """The characters Mattermost keeps in one word: ``:.-_@``, letters and digits of any script."""
    return char in ":.-_@" or unicodedata.category(char)[0] in "LN"


def _words(text: str) -> list[str]:
    return "".join(char if _is_word_character(char) else " " for char in text).split()


def _is_system_mention(word: str) -> bool:
    return word.lower() in _SYSTEM_MENTIONS


_SENTENCE_PUNCTUATION_RE = re.compile(r"[.\-:]")


def _everyone_is_mentioned(text: str) -> bool:
    """Port of the server's ``StandardMentionParser.ProcessText``, limited to the three channel-wide words.

    Source: mattermost/server/channels/app/mention_parser_standard.go. A word is checked after its leading
    ``:.-_`` are trimmed, again as its trailing ``.-:_`` are trimmed one by one, and, unless it starts with ``@``,
    in the pieces it splits into at ``.``, ``-`` and ``:``.
    """
    for word in _words(text):
        if word[0] == ":" and word[-1] == ":":
            continue
        word = word.lstrip(":.-_")
        if _is_system_mention(word):
            return True
        trimmed = word
        while trimmed and trimmed[-1] in ".-:_":
            trimmed = trimmed[:-1]
            if _is_system_mention(trimmed):
                return True
        if not word.startswith("@") and any(_is_system_mention(piece) for piece in _SENTENCE_PUNCTUATION_RE.split(word)):
            return True
    return False


def _post_notifies_everyone(text: str) -> bool:
    """The server parses a post as Markdown first, which turns character references like ``&#64;`` into text."""
    return _everyone_is_mentioned(text) or _everyone_is_mentioned(html.unescape(text))


_BROADCASTS = ["@channel", "@all", "@here", "@CHANNEL", "@Here"]
_CONTEXTS = [
    "{}",
    "Heads up {} please read",
    "({})",
    "line one\n{}\nline three",
    "```\n{}\n```",
    "{}, then {}!",
    "_{}_",
    "__{}__",
    "*{}*",
    "**{}**",
    "{}_",
    "{}__.",
    "{}_-",
    "-_{}",
    "x-{}",
    "x.{}",
    "x:{}",
]


@pytest.mark.parametrize("template", _CONTEXTS)
@pytest.mark.parametrize("word", _BROADCASTS)
def test_a_broadcast_mention_no_longer_notifies(word: str, template: str) -> None:
    text = template.format(*([word] * template.count("{}")))

    neutral = neutralize_broadcast_mentions(text)

    assert _post_notifies_everyone(text)
    assert not _post_notifies_everyone(neutral)
    assert neutral.replace(_ZWSP, "") == text


@pytest.mark.parametrize(
    "text",
    [
        "&#64;here",
        "&#x40;channel",
        "&#X40;all",
        "&#0064;here",
        "&commat;channel",
        "@h&#101;re",
        "&#64;&#104;ere",
        "&#x40;&#x61;&#x6c;&#x6c;",
        "ping &#64;all now",
        "_&#64;here_",
    ],
)
def test_a_mention_written_as_character_references_no_longer_notifies(text: str) -> None:
    neutral = neutralize_broadcast_mentions(text)

    assert _post_notifies_everyone(text)
    assert not _post_notifies_everyone(neutral)
    assert neutral.replace(_ZWSP, "") == text


@pytest.mark.parametrize(
    "text",
    [
        "mail bob@here.com",
        "ping @alice",
        "@channels",
        "@allison",
        "@here_team",
        "@all_users",
        "@channel_id and @here2",
        "user@all",
        "x@channel",
        "&#64;alice and &#64;here_team",
        "&amp;here and &commat;",
        "no mention at all",
        "",
    ],
)
def test_text_that_does_not_notify_a_channel_is_left_as_it_is(text: str) -> None:
    assert not _post_notifies_everyone(text)
    assert neutralize_broadcast_mentions(text) == text


def test_neutralizing_twice_changes_nothing() -> None:
    once = neutralize_broadcast_mentions("@here and @all and @channel and &#64;here and _@here_")

    assert neutralize_broadcast_mentions(once) == once


_PIECES = [
    "@here",
    "@all",
    "@channel",
    "@HERE",
    "&#64;here",
    "&commat;all",
    "@h&#101;re",
    "_",
    ".",
    "-",
    ":",
    " ",
    "a",
    "1",
    "\u5927",
    "*",
    "`",
    "\n",
]


def test_no_text_made_of_mentions_and_the_characters_around_them_notifies_after_neutralizing() -> None:
    """Every combination of up to four pieces, checked against the server's splitter."""
    leaks = []
    for length in range(1, 5):
        for pieces in itertools.product(_PIECES, repeat=length):
            text = "".join(pieces)
            if _post_notifies_everyone(neutralize_broadcast_mentions(text)):
                leaks.append(text)

    assert leaks == []


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
