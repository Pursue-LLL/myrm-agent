"""A reply leaves the renderer without NUL and without surrogate code points, whatever the channel's format.

NUL is the marker the converters put around the code they set aside, and a lone surrogate cannot be encoded as UTF-8:
a byte-limit splitter, a card slicer or a JSON body that meets one raises and the reply is lost.
"""

from __future__ import annotations

import random

import pytest

import app.channels.providers.slack  # noqa: F401  # registers the mrkdwn converter
import app.channels.providers.whatsapp  # noqa: F401  # registers the whatsapp converter
from app.channels.providers.feishu.table_slicer import slice_card_markdown
from app.channels.providers.telegram.html_converter import md_to_telegram_html, split_markdown_rich
from app.channels.providers.telegram.html_converter import split_message as split_telegram_html
from app.channels.rendering.renderer import render
from app.channels.rendering.text_utils import scrub_unsendable_chars
from app.channels.types import LengthUnit, OutboundMessage, ReasoningDisplay, RenderStyle, ToolStep, ToolSummaryDisplay


def _message(
    content: str,
    *,
    reasoning: str | None = None,
    tool_steps: tuple[ToolStep, ...] = (),
    metadata: dict[str, object] | None = None,
) -> OutboundMessage:
    return OutboundMessage(
        channel="test",
        recipient_id="u1",
        content=content,
        user_id="u1",
        reasoning=reasoning,
        tool_steps=tool_steps,
        metadata=metadata,
    )


def _style(
    fmt: str = "markdown",
    *,
    max_text_length: int = 4096,
    length_unit: LengthUnit = "chars",
    supports_latex: bool = False,
    supports_tables: bool = False,
    supports_expandable_blockquote: bool = False,
) -> RenderStyle:
    """A style that shows every part of a reply: the reasoning inline, the tool steps in full."""
    return RenderStyle(
        format=fmt,
        max_text_length=max_text_length,
        length_unit=length_unit,
        supports_latex=supports_latex,
        supports_tables=supports_tables,
        supports_expandable_blockquote=supports_expandable_blockquote,
        reasoning_display=ReasoningDisplay.INLINE,
        tool_summary_display=ToolSummaryDisplay.DETAILED,
    )


def _expected_scrub(text: str) -> str:
    """The scrub written out separately: NUL dropped, a high half and the low half after it joined, the rest replaced."""
    chars = [char for char in text if char != "\x00"]
    result: list[str] = []
    index = 0
    while index < len(chars):
        code = ord(chars[index])
        if 0xD800 <= code < 0xDC00 and index + 1 < len(chars) and 0xDC00 <= ord(chars[index + 1]) < 0xE000:
            result.append(chr(0x10000 + ((code - 0xD800) << 10) + (ord(chars[index + 1]) - 0xDC00)))
            index += 2
            continue
        result.append("\ufffd" if 0xD800 <= code < 0xE000 else chars[index])
        index += 1
    return "".join(result)


class TestScrubUnsendableChars:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("", ""),
            ("plain text", "plain text"),
            ("中文 and emoji \U0001f600", "中文 and emoji \U0001f600"),
            ("a\x00b\x00", "ab"),
            ("x\ud800y", "x\ufffdy"),
            ("x\udc00y", "x\ufffdy"),
            ("pair \ud83d\ude00 end", "pair \U0001f600 end"),
            ("\ude00\ud83d", "\ufffd\ufffd"),
            ("\ud83d\ud83d", "\ufffd\ufffd"),
            ("\ud83dA", "\ufffdA"),
            ("\ud83d\x00\ude00", "\U0001f600"),
        ],
    )
    def test_text_is_scrubbed(self, text: str, expected: str) -> None:
        assert scrub_unsendable_chars(text) == expected

    def test_random_text_matches_an_independent_scrub_and_is_encodable_and_stable(self) -> None:
        alphabet = ["a", "Z", " ", "\n", "中", "\U0001f600", "\x00", "\ud83d", "\ude00", "\ud800", "\udfff", "`", "*"]
        for seed in range(3000):
            rng = random.Random(seed)
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
            scrubbed = scrub_unsendable_chars(text)
            assert scrubbed == _expected_scrub(text), f"seed {seed}: {text!r}"
            scrubbed.encode("utf-8")
            assert "\x00" not in scrubbed
            assert scrub_unsendable_chars(scrubbed) == scrubbed


class TestRenderedText:
    _STYLES = {
        "markdown": _style("markdown"),
        "plaintext": _style("plaintext"),
        "mrkdwn": _style("mrkdwn"),
        "whatsapp": _style("whatsapp"),
    }

    @staticmethod
    def _reply_with_unsendable_chars() -> OutboundMessage:
        return _message(
            "body \ud83d lone, nul \x00 here, pair \ud83d\ude00 ok",
            reasoning="thinks \udc00 hard",
            tool_steps=(ToolStep(name="search", label="Sea\x00rch", detail="q=\ud800"),),
            metadata={
                "sources": [{"index": 1, "title": "Ti\ud800tle", "url": "https://example.com/\x00a"}],
                "cost_metadata": {"cost_usd": 0.5, "model_name": "mod\udc00el", "total_tokens": 1500},
            },
        )

    @pytest.mark.parametrize("name", sorted(_STYLES))
    def test_every_part_of_the_reply_is_scrubbed(self, name: str) -> None:
        text = "".join(render(self._reply_with_unsendable_chars(), self._STYLES[name]))

        text.encode("utf-8")
        assert "\x00" not in text
        assert "body \ufffd lone, nul  here, pair \U0001f600 ok" in text
        for scrubbed_part in ("thinks \ufffd hard", "Search", "q=\ufffd", "Ti\ufffdtle", "https://example.com/a", "mod\ufffdel"):
            assert scrubbed_part in text, f"{scrubbed_part!r} missing from {text!r}"

    @pytest.mark.parametrize("name", sorted(_STYLES))
    def test_every_chunk_of_a_split_reply_is_encodable(self, name: str) -> None:
        style = _style(self._STYLES[name].format, max_text_length=90, length_unit="utf8")
        chunks = render(self._reply_with_unsendable_chars(), style)

        assert len(chunks) > 1
        for chunk in chunks:
            chunk.encode("utf-8")
            assert "\x00" not in chunk

    def test_a_reply_of_nothing_but_nul_is_the_empty_reply(self) -> None:
        assert render(_message("\x00\x00"), self._STYLES["markdown"]) == ["Done."]

    def test_a_nul_in_the_text_is_not_taken_for_a_set_aside_code_block(self) -> None:
        # Unscrubbed, the NUL-fenced "FENCE0" in the prose would be put back as the code block, doubling it.
        reply = _message("see \x00FENCE0\x00 here\n```\ncode\n```")

        assert render(reply, self._STYLES["whatsapp"]) == ["see FENCE0 here\n```\ncode\n```"]


class TestConsumersOfRenderedText:
    """The splitters, converters and slicers that read what ``render`` returns never meet a character they cannot encode."""

    _LONG = "段落 ☃ \ud83d lone \x00 nul `code`\n\n" * 2500

    def test_the_telegram_rich_splitter_reads_it(self) -> None:
        style = _style("markdown", max_text_length=32000, supports_latex=True, supports_tables=True)
        parts = [part for chunk in render(_message(self._LONG), style) for part in split_markdown_rich(chunk)]

        assert parts
        assert all(len(part.encode("utf-8")) <= 32000 for part in parts)

    def test_the_telegram_html_splitter_reads_it(self) -> None:
        chunks = render(_message(self._LONG), _style("markdown", supports_expandable_blockquote=True))
        parts = [part for chunk in chunks for part in split_telegram_html(md_to_telegram_html(chunk))]

        assert parts
        assert all(part.encode("utf-16-le") for part in parts)

    def test_the_feishu_card_slicer_reads_it(self) -> None:
        chunks = render(_message(self._LONG), _style("markdown", max_text_length=40000))
        slices = [piece for chunk in chunks for piece in slice_card_markdown(chunk, max_bytes=2000)]

        assert len(slices) > 1
