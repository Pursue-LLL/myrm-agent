"""A Slack message with buttons shows its text above them, however it is delivered.

Once a message carries blocks, Slack renders only the blocks and uses ``text`` for notifications alone, so the
body has to be a block of its own. The same holds when a placeholder is edited into the final reply, and when
Slack refuses the blocks the text must still get through.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import cast
from unittest.mock import patch

import httpx
import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.slack import SlackChannel
from app.channels.providers.slack.helpers import build_message_blocks
from app.channels.types import ActionButton, OutboundMessage, QuickReply, SelectMenu

_BUTTON = ((ActionButton(label="Approve", action_id="approve"),),)
_BLOCK_ERRORS = ["invalid_blocks", "invalid_blocks_format", "msg_blocks_too_long"]

Call = tuple[str, dict[str, object]]


def _channel() -> SlackChannel:
    channel = SlackChannel(bot_token="xoxb-test", app_token="xapp-test")
    channel._bot_user_id = "U_BOT"
    return channel


def _message(
    content: str,
    *,
    components: tuple[tuple[ActionButton | SelectMenu, ...], ...] = (),
    quick_replies: tuple[QuickReply, ...] = (),
) -> OutboundMessage:
    return OutboundMessage(
        channel="slack",
        recipient_id="C1",
        content=content,
        user_id="U1",
        components=components,
        quick_replies=quick_replies,
    )


async def _record(run: Callable[[SlackChannel], Awaitable[object]], replies: Sequence[dict[str, object]]) -> list[Call]:
    """Run ``run(channel)`` against a Slack that answers with ``replies`` in turn; every call it received."""
    channel = _channel()
    calls: list[Call] = []
    pending = list(replies)

    async def answer(url: str, *, json: dict[str, object], **_: object) -> httpx.Response:
        calls.append((url.rsplit("/", 1)[-1], json))
        return httpx.Response(200, json=pending.pop(0) if pending else {"ok": True, "ts": "1.1"})

    with patch.object(channel._api._http, "post", side_effect=answer):
        await run(channel)
    return calls


def _blocks(call: Call) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", call[1]["blocks"])


def _section_text(block: dict[str, object]) -> str:
    return cast("dict[str, str]", block["text"])["text"]


class TestBuildMessageBlocks:
    def test_a_message_without_interactive_elements_has_no_blocks(self) -> None:
        assert build_message_blocks("plain", _message("plain")) is None

    def test_the_body_comes_first_and_the_buttons_after_it(self) -> None:
        blocks = build_message_blocks("Pick one", _message("Pick one", components=_BUTTON))

        assert blocks is not None
        assert [block["type"] for block in blocks] == ["section", "actions"]
        assert blocks[0]["text"] == {"type": "mrkdwn", "text": "Pick one"}

    def test_quick_replies_count_as_interactive_elements(self) -> None:
        blocks = build_message_blocks("Yes or no?", _message("Yes or no?", quick_replies=(QuickReply(label="Yes", text="yes"),)))

        assert blocks is not None
        assert [block["type"] for block in blocks] == ["section", "actions"]

    def test_a_body_beyond_the_section_limit_becomes_several_sections(self) -> None:
        body = "word " * 1500
        blocks = build_message_blocks(body, _message(body, components=_BUTTON))

        assert blocks is not None
        sections = [block for block in blocks if block["type"] == "section"]
        assert len(sections) == 3
        assert all(len(_section_text(section)) <= 3000 for section in sections)
        assert "".join("".join(_section_text(s).split()) for s in sections) == "".join(body.split())
        assert blocks[-1]["type"] == "actions"

    def test_an_empty_body_leaves_only_the_buttons(self) -> None:
        blocks = build_message_blocks("", _message("", components=_BUTTON))

        assert blocks is not None
        assert [block["type"] for block in blocks] == ["actions"]


class TestSend:
    @pytest.mark.asyncio
    async def test_the_text_of_a_message_with_buttons_is_a_block(self) -> None:
        calls = await _record(lambda ch: ch.send(_message("Approve the plan?", components=_BUTTON)), [])

        assert [name for name, _ in calls] == ["chat.postMessage"]
        assert [block["type"] for block in _blocks(calls[0])] == ["section", "actions"]
        assert _section_text(_blocks(calls[0])[0]) == "Approve the plan?"
        assert calls[0][1]["text"] == "Approve the plan?"

    @pytest.mark.asyncio
    async def test_a_message_without_buttons_carries_no_blocks(self) -> None:
        calls = await _record(lambda ch: ch.send(_message("Just text")), [])

        assert "blocks" not in calls[0][1]

    @pytest.mark.asyncio
    async def test_only_the_last_part_of_a_long_reply_carries_the_buttons(self) -> None:
        body = "sentence. " * 1200
        calls = await _record(lambda ch: ch.send(_message(body, components=_BUTTON)), [])

        assert len(calls) == 3
        assert all("blocks" not in call[1] for call in calls[:-1])
        assert [block["type"] for block in _blocks(calls[-1])][-1] == "actions"
        last_text = cast("str", calls[-1][1]["text"])
        assert "".join(_section_text(b) for b in _blocks(calls[-1]) if b["type"] == "section").strip() == last_text.strip()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error", _BLOCK_ERRORS)
    async def test_blocks_slack_refuses_are_dropped_and_the_text_is_posted(self, error: str) -> None:
        calls = await _record(
            lambda ch: ch.send(_message("Approve the plan?", components=_BUTTON)),
            [{"ok": False, "error": error}, {"ok": True, "ts": "7.7"}],
        )

        assert [name for name, _ in calls] == ["chat.postMessage", "chat.postMessage"]
        assert "blocks" in calls[0][1]
        assert "blocks" not in calls[1][1]
        assert calls[1][1]["text"] == "Approve the plan?"

    @pytest.mark.asyncio
    async def test_the_ts_of_the_retried_post_is_returned(self) -> None:
        channel = _channel()
        replies = iter([{"ok": False, "error": "invalid_blocks"}, {"ok": True, "ts": "7.7"}])

        async def answer(url: str, **_: object) -> httpx.Response:
            return httpx.Response(200, json=next(replies))

        with patch.object(channel._api._http, "post", side_effect=answer):
            assert await channel.send(_message("Approve?", components=_BUTTON)) == "7.7"

    @pytest.mark.asyncio
    async def test_any_other_refusal_is_raised_without_a_second_post(self) -> None:
        channel = _channel()
        calls: list[str] = []

        async def answer(url: str, **_: object) -> httpx.Response:
            calls.append(url)
            return httpx.Response(200, json={"ok": False, "error": "channel_not_found"})

        with patch.object(channel._api._http, "post", side_effect=answer):
            with pytest.raises(ChannelSendError, match="channel_not_found"):
                await channel.send(_message("Approve?", components=_BUTTON))
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_a_text_only_message_refused_for_blocks_is_raised(self) -> None:
        channel = _channel()
        calls: list[str] = []

        async def answer(url: str, **_: object) -> httpx.Response:
            calls.append(url)
            return httpx.Response(200, json={"ok": False, "error": "invalid_blocks"})

        with patch.object(channel._api._http, "post", side_effect=answer):
            with pytest.raises(ChannelSendError, match="invalid_blocks"):
                await channel.send(_message("plain"))
        assert len(calls) == 1


class TestEditPlaceholder:
    @pytest.mark.asyncio
    async def test_the_final_reply_keeps_its_buttons(self) -> None:
        calls = await _record(lambda ch: ch.edit_placeholder_message("C1", "9.9", _message("Approve?", components=_BUTTON)), [])

        assert [name for name, _ in calls] == ["chat.update"]
        assert [block["type"] for block in _blocks(calls[0])] == ["section", "actions"]
        assert _section_text(_blocks(calls[0])[0]) == "Approve?"
        assert calls[0][1]["text"] == "Approve?"

    @pytest.mark.asyncio
    async def test_a_final_reply_without_buttons_is_text_only(self) -> None:
        calls = await _record(lambda ch: ch.edit_placeholder_message("C1", "9.9", _message("Done.")), [])

        assert calls[0][1]["text"] == "Done."
        assert "blocks" not in calls[0][1]

    @pytest.mark.asyncio
    async def test_the_body_block_cannot_notify_the_channel(self) -> None:
        calls = await _record(
            lambda ch: ch.edit_placeholder_message("C1", "9.9", _message("ping <!channel>", components=_BUTTON)), []
        )

        assert _section_text(_blocks(calls[0])[0]) == "ping &lt;!channel&gt;"
        assert calls[0][1]["text"] == "ping &lt;!channel&gt;"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error", _BLOCK_ERRORS)
    async def test_blocks_slack_refuses_are_dropped_and_the_text_replaces_the_placeholder(self, error: str) -> None:
        calls = await _record(
            lambda ch: ch.edit_placeholder_message("C1", "9.9", _message("Approve?", components=_BUTTON)),
            [{"ok": False, "error": error}, {"ok": True}],
        )

        assert [name for name, _ in calls] == ["chat.update", "chat.update"]
        assert "blocks" in calls[0][1]
        assert "blocks" not in calls[1][1]
        assert calls[1][1]["text"] == "Approve?"
