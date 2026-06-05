"""Unit tests for Telegram Markdown -> HTML converter."""

from __future__ import annotations

from app.channels.providers.telegram.html_converter import (
    md_to_telegram_html,
    split_message,
)


class TestMdToTelegramHtml:
    def test_plain_text_escapes_html(self) -> None:
        assert md_to_telegram_html("a < b & c > d") == "a &lt; b &amp; c &gt; d"

    def test_bold(self) -> None:
        assert md_to_telegram_html("**bold**") == "<b>bold</b>"

    def test_italic(self) -> None:
        assert md_to_telegram_html("*italic*") == "<i>italic</i>"

    def test_strikethrough(self) -> None:
        assert md_to_telegram_html("~~strike~~") == "<s>strike</s>"

    def test_inline_code(self) -> None:
        result = md_to_telegram_html("`code`")
        assert result == "<code>code</code>"

    def test_inline_code_escapes_html(self) -> None:
        result = md_to_telegram_html("`<script>`")
        assert "&lt;script&gt;" in result
        assert "<code>" in result

    def test_code_block_no_lang(self) -> None:
        result = md_to_telegram_html("```\nprint('hi')\n```")
        assert "<pre>" in result
        assert "print(&#x27;hi&#x27;)" in result

    def test_code_block_with_lang(self) -> None:
        result = md_to_telegram_html("```python\nprint('hi')\n```")
        assert 'class="language-python"' in result

    def test_link(self) -> None:
        result = md_to_telegram_html("[Google](https://google.com)")
        assert '<a href="https://google.com">Google</a>' in result

    def test_mixed_formatting(self) -> None:
        result = md_to_telegram_html("**bold** and *italic* and `code`")
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result
        assert "<code>code</code>" in result

    def test_empty_string(self) -> None:
        assert md_to_telegram_html("") == ""

    def test_no_markdown(self) -> None:
        assert md_to_telegram_html("hello world") == "hello world"

    def test_code_block_preserves_content(self) -> None:
        result = md_to_telegram_html("```\n**not bold**\n```")
        assert "<b>" not in result
        assert "**not bold**" in result

    def test_html_entities_in_text(self) -> None:
        result = md_to_telegram_html("Tom & Jerry <3")
        assert "&amp;" in result
        assert "&lt;3" in result

    def test_bold_italic_adjacent(self) -> None:
        result = md_to_telegram_html("**bold** *italic*")
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result


class TestSplitMessage:
    def test_short_message_no_split(self) -> None:
        assert split_message("hello") == ["hello"]

    def test_exact_limit(self) -> None:
        text = "a" * 4096
        assert split_message(text) == [text]

    def test_splits_at_newline(self) -> None:
        text = "a" * 4000 + "\n" + "b" * 200
        chunks = split_message(text, limit=4096)
        assert len(chunks) == 2
        assert chunks[0] == "a" * 4000 + "\n"
        assert chunks[1] == "b" * 200

    def test_splits_at_limit_when_no_newline(self) -> None:
        text = "a" * 5000
        chunks = split_message(text, limit=4096)
        assert len(chunks) == 2
        assert len(chunks[0]) == 4096

    def test_surrogate_pair_protection(self) -> None:
        emoji = "\U0001f600"
        text = "a" + emoji
        chunks = split_message(text, limit=2)
        assert chunks == ["a", emoji]

        text = "a" * 4095 + emoji
        chunks = split_message(text, limit=4096)
        assert len(chunks) == 2
        assert chunks[0] == "a" * 4095
        assert chunks[1] == emoji

    def test_html_tag_auto_close_and_reopen(self) -> None:
        # Test that tags are closed at chunk boundary and reopened in the next chunk
        text = "<b>" + "a" * 4000 + "</b>"
        chunks = split_message(text, limit=2000)
        assert len(chunks) >= 2
        assert chunks[0].startswith("<b>")
        assert chunks[0].endswith("</b>")
        assert chunks[1].startswith("<b>")

        # Test nested tags
        text = "<b><i>" + "a" * 4000 + "</i></b>"
        chunks = split_message(text, limit=2000)
        assert chunks[0].endswith("</i></b>")
        assert chunks[1].startswith("<b><i>")

    def test_empty_string(self) -> None:
        assert split_message("") == [""]

    def test_custom_limit(self) -> None:
        text = "hello world"
        chunks = split_message(text, limit=5)
        assert len(chunks) >= 2
