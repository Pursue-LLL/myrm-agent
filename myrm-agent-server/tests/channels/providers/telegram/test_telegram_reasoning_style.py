"""Telegram's two render styles each keep the form they give a collapsed reasoning.

The plain style sends HTML, where ``<blockquote expandable>`` is a quote the reader can fold; the rich style converts
Markdown itself, so its reasoning is an ordinary Markdown quote.
"""

from __future__ import annotations

from app.channels.providers.telegram.channel import TelegramChannel
from app.channels.rendering.renderer import render
from app.channels.types import OutboundMessage

_REASONING = "weighing two options"


def _reply() -> OutboundMessage:
    return OutboundMessage(channel="telegram", recipient_id="42", content="The answer", user_id="u1", reasoning=_REASONING)


def test_the_plain_style_sends_the_reasoning_as_an_expandable_blockquote() -> None:
    text = render(_reply(), TelegramChannel.render_style)[0]

    assert text.startswith(f"<blockquote expandable>\U0001f9e0 Thinking\n\n{_REASONING}\n</blockquote>")


def test_the_rich_style_sends_the_reasoning_as_a_markdown_quote() -> None:
    text = render(_reply(), TelegramChannel._rich_render_style)[0]

    assert text.startswith(f"> \U0001f9e0 **Thinking**\n>\n> {_REASONING}")
    assert "<blockquote" not in text
