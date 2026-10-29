"""Slack text that comes from the agent cannot notify a whole channel, workspace or user group.

``<!here>``, ``<!channel>``, ``<!everyone>`` and ``<!subteam^ID>`` notify people when they reach Slack
unescaped, in any text the bot sends: the rendered final reply and the raw placeholder or stream text alike.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.channels.providers.slack import SlackChannel
from app.channels.providers.slack.format_converter import md_to_slack_mrkdwn, neutralize_broadcast_mentions
from app.channels.rendering.renderer import render
from app.channels.types import OutboundMessage

_BROADCASTS = [
    "<!here>",
    "<!channel>",
    "<!everyone>",
    "<!subteam^S123>",
    "<!subteam^S123|@oncall>",
    "<!channel|channel>",
    "<!HERE>",
]
_BROADCAST_ANYWHERE = re.compile(r"<!(?:here|channel|everyone|subteam)", re.IGNORECASE)


def _notifies(text: str) -> bool:
    return _BROADCAST_ANYWHERE.search(text) is not None


@pytest.mark.parametrize("token", _BROADCASTS)
def test_a_broadcast_token_in_the_reply_is_escaped(token: str) -> None:
    converted = md_to_slack_mrkdwn(f"Heads up {token} please read")

    assert not _notifies(converted)
    assert "Heads up &lt;!" in converted
    assert converted.endswith("please read")


@pytest.mark.parametrize("target", ["!channel", "!here", "!everyone", "@here", "@channel", "#general", "!subteam^S123"])
def test_a_markdown_link_cannot_aim_at_a_mention_or_channel(target: str) -> None:
    converted = md_to_slack_mrkdwn(f"[ping all]({target}) now")

    assert converted == "ping all now"


@pytest.mark.parametrize("token", _BROADCASTS)
def test_a_broadcast_token_in_a_link_label_is_escaped(token: str) -> None:
    converted = md_to_slack_mrkdwn(f"[{token}](https://example.com/x)")

    assert not _notifies(converted)
    assert converted.startswith("<https://example.com/x|&lt;!")


@pytest.mark.parametrize("token", _BROADCASTS)
def test_a_broadcast_token_inside_a_code_fence_is_escaped(token: str) -> None:
    converted = md_to_slack_mrkdwn(f"```\n{token}\n<div>x</div>\n```")

    assert not _notifies(converted)
    assert "<div>x</div>" in converted


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("Hello <@U123456>", "Hello <@U123456>"),
        ("See <#C123456>", "See <#C123456>"),
        ("[docs](https://example.com/a)", "<https://example.com/a|docs>"),
        ("[mail me](mailto:a@example.com)", "<mailto:a@example.com|mail me>"),
        ("<https://example.com> and <tel:+1234567890>", "<https://example.com> and <tel:+1234567890>"),
        ("<!date^1392734382^{date_num}|Feb 18>", "<!date^1392734382^{date_num}|Feb 18>"),
        ("R&D <b>bold</b>", "R&amp;D &lt;b&gt;bold&lt;/b&gt;"),
        ("**bold** and !channel and @here", "*bold* and !channel and @here"),
    ],
)
def test_everything_else_is_left_as_it_was(markdown: str, expected: str) -> None:
    assert md_to_slack_mrkdwn(markdown) == expected


def test_the_final_reply_the_channel_renders_cannot_notify() -> None:
    channel = SlackChannel(bot_token="xoxb-test", app_token="xapp-test")
    reply = OutboundMessage(channel="slack", recipient_id="C1", content="Done <!channel> [all](!here) <!subteam^S1>", user_id="u")

    (chunk,) = render(reply, channel.render_style)

    assert not _notifies(chunk)


def test_neutralizing_is_idempotent_and_touches_only_broadcasts() -> None:
    raw = "a <!channel> b <@U1> c <!date^1^{date}|d> e <!subteam^S1|@t> f &amp; g"

    once = neutralize_broadcast_mentions(raw)

    assert neutralize_broadcast_mentions(once) == once
    assert once == "a &lt;!channel&gt; b <@U1> c <!date^1^{date}|d> e &lt;!subteam^S1|@t&gt; f &amp; g"


def _channel() -> SlackChannel:
    channel = SlackChannel(bot_token="xoxb-test", app_token="xapp-test")
    channel._bot_user_id = "U_BOT"
    channel._team_id = "T_TEAM"
    return channel


def _calls(post: AsyncMock, method: str) -> list[dict[str, object]]:
    return [call.kwargs["json"] for call in post.await_args_list if str(call.args[0]).endswith(f"/{method}")]


def _ok(**extra: object) -> AsyncMock:
    return AsyncMock(return_value=httpx.Response(200, json={"ok": True, **extra}))


class TestRawTextBeforeItIsRendered:
    """The placeholder and the progress edits send agent text that no converter has seen."""

    @pytest.mark.asyncio
    async def test_a_placeholder_started_as_a_stream(self) -> None:
        channel, post = _channel(), _ok(ts="1.1")

        with patch.object(channel._api._http, "post", post):
            await channel.send_placeholder("C1", "Looking <!channel> up <@U123>", thread_id="9.9")

        (start,) = _calls(post, "chat.startStream")
        assert start["markdown_text"] == "Looking &lt;!channel&gt; up <@U123>"

    @pytest.mark.asyncio
    async def test_a_placeholder_posted_as_a_message(self) -> None:
        channel, post = _channel(), _ok(ts="1.1")

        with patch.object(channel._api._http, "post", post):
            await channel.send_placeholder("C1", "Looking <!everyone> up")

        (posted,) = _calls(post, "chat.postMessage")
        assert posted["text"] == "Looking &lt;!everyone&gt; up"

    @pytest.mark.asyncio
    async def test_a_progress_edit_that_extends_the_stream_appends_only_the_new_text(self) -> None:
        channel, post = _channel(), _ok(ts="1.1")

        with patch.object(channel._api._http, "post", post):
            await channel.send_placeholder("C1", "step <!here>", thread_id="9.9")
            await channel.edit_message("C1", "1.1", "step <!here> then more <!subteam^S1>")

        (append,) = _calls(post, "chat.appendStream")
        assert append["markdown_text"] == " then more &lt;!subteam^S1&gt;"

    @pytest.mark.asyncio
    async def test_a_token_that_completes_between_edits_replaces_the_text_instead_of_appending(self) -> None:
        channel, post = _channel(), _ok(ts="1.1")

        with patch.object(channel._api._http, "post", post):
            await channel.send_placeholder("C1", "see <!chan", thread_id="9.9")
            await channel.edit_message("C1", "1.1", "see <!channel> now")

        assert not _calls(post, "chat.appendStream")
        (update,) = _calls(post, "chat.update")
        assert update["text"] == "see &lt;!channel&gt; now"

    @pytest.mark.asyncio
    async def test_an_edit_of_a_plain_message(self) -> None:
        channel, post = _channel(), _ok()

        with patch.object(channel._api._http, "post", post):
            await channel.edit_message("C1", "5.5", "now <!channel>")

        (update,) = _calls(post, "chat.update")
        assert update["text"] == "now &lt;!channel&gt;"

    @pytest.mark.asyncio
    async def test_a_final_reply_ending_a_stream_is_neutral_too(self) -> None:
        channel, post = _channel(), _ok()
        channel._stream_sent["1.1"] = "partial"
        reply = OutboundMessage(channel="slack", recipient_id="C1", content="Done <!channel>", user_id="u")

        with patch.object(channel._api._http, "post", post):
            await channel.edit_placeholder_message("C1", "1.1", reply)

        (stop,) = _calls(post, "chat.stopStream")
        assert not _notifies(str(stop["markdown_text"]))
