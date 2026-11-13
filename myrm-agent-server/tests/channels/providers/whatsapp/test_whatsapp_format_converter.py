"""Unit tests for WhatsApp format converter."""

from __future__ import annotations

import random
import time

import pytest

from app.channels.providers.whatsapp.format_converter import (
    md_to_whatsapp,
    validate_whatsapp_format,
)


class TestMarkdownToWhatsApp:
    """Tests for md_to_whatsapp() conversion."""

    def test_empty_string(self) -> None:
        assert md_to_whatsapp("") == ""

    def test_bold_double_star(self) -> None:
        assert md_to_whatsapp("**bold**") == "*bold*"

    def test_bold_double_underscore(self) -> None:
        assert md_to_whatsapp("__bold__") == "*bold*"

    def test_strikethrough(self) -> None:
        assert md_to_whatsapp("~~strike~~") == "~strike~"

    def test_mixed_formatting(self) -> None:
        text = "**bold** and ~~strike~~ and __more bold__"
        expected = "*bold* and ~strike~ and *more bold*"
        assert md_to_whatsapp(text) == expected

    def test_preserves_inline_code(self) -> None:
        text = "Code: `print('hello')` here"
        assert md_to_whatsapp(text) == text

    def test_preserves_code_fence(self) -> None:
        text = "Example:\n```python\nprint('hello')\n```\nDone."
        assert md_to_whatsapp(text) == text

    def test_code_fence_with_formatting(self) -> None:
        text = "**before** ```code**here**``` **after**"
        expected = "*before* ```code**here**``` *after*"
        assert md_to_whatsapp(text) == expected

    def test_inline_code_with_formatting(self) -> None:
        text = "**before** `code**here**` **after**"
        expected = "*before* `code**here**` *after*"
        assert md_to_whatsapp(text) == expected

    def test_complex_scenario(self) -> None:
        text = """**Title**

This is ~~deleted~~ content with `inline_code` and __bold__.

```python
def foo():
    return "**not bold**"
```

Done."""
        expected = """*Title*

This is ~deleted~ content with `inline_code` and *bold*.

```python
def foo():
    return "**not bold**"
```

Done."""
        assert md_to_whatsapp(text) == expected

    def test_no_formatting(self) -> None:
        text = "Plain text without any formatting"
        assert md_to_whatsapp(text) == text

    def test_multiple_code_fences(self) -> None:
        text = "```a```\n**bold**\n```b```"
        expected = "```a```\n*bold*\n```b```"
        assert md_to_whatsapp(text) == expected


class TestCodeComesBackWhole:
    """Code is set aside while the text around it is converted, and put back exactly as it was written."""

    @pytest.mark.parametrize(
        "text",
        [
            "Use `x`5 times",
            "Run `ls`10 times and `cd`",
            "Size is `n`2",
            "a `b`1 and `c` and `d`",
            "```\nx\n```5",
            "```a```12 and ```b```3",
        ],
    )
    def test_a_digit_right_after_code_is_not_part_of_its_place(self, text: str) -> None:
        assert md_to_whatsapp(text) == text

    def test_more_than_ten_code_spans_each_come_back_in_its_own_place(self) -> None:
        text = " ".join(f"`c{i}`{i}" for i in range(13))
        assert md_to_whatsapp(text) == text

    def test_a_span_that_surrounds_a_fence_on_one_line_comes_back_whole(self) -> None:
        text = "a ` b ```py\nx\n``` c ` d"
        assert md_to_whatsapp(text) == text

    def test_the_text_around_code_that_is_followed_by_a_digit_is_still_converted(self) -> None:
        assert md_to_whatsapp("**bold** `x`5 ~~gone~~") == "*bold* `x`5 ~gone~"

    def test_the_blocks_a_longer_fence_documents_are_not_formatted(self) -> None:
        text = "Example:\n\n````markdown\n**one** and [a](http://x.y)\n```bash\n**two**\n```\n**three**\n````\n\nEnd **bold**."
        expected = "Example:\n\n````markdown\n**one** and [a](http://x.y)\n```bash\n**two**\n```\n**three**\n````\n\nEnd *bold*."
        assert md_to_whatsapp(text) == expected

    def test_a_degenerate_line_of_backticks_is_converted_in_linear_time(self) -> None:
        # Tried at every offset against every length, a run of thousands of backticks takes seconds.
        degenerate = "`" * 8_000 + "a\n" + "x" * 8_000
        started = time.perf_counter()
        assert md_to_whatsapp(degenerate)
        assert time.perf_counter() - started < 2.0

    def test_random_documents_keep_every_code_piece_and_convert_the_rest(self) -> None:
        words = ("alpha", "beta", "gamma", "7", "42")
        for seed in range(1000):
            rng = random.Random(seed)
            pieces: list[tuple[str, str]] = []
            for _ in range(rng.randint(1, 8)):
                kind = rng.choice(("prose", "inline", "inline_digit", "fence", "fence_digit", "long_fence"))
                word = rng.choice(words)
                if kind == "prose":
                    pieces.append((f"**{word}** and ~~{word}~~", f"*{word}* and ~{word}~"))
                elif kind.startswith("inline"):
                    code = f"`**{word}**`" + (rng.choice(words) if kind == "inline_digit" else "")
                    pieces.append((f"see {code} now", f"see {code} now"))
                else:
                    fence = "````" if kind == "long_fence" else "```"
                    inner = "```\n**in**\n```\n" if kind == "long_fence" else ""
                    code = f"{fence}py\n**{word}**\n{inner}{fence}" + (rng.choice(words) if kind == "fence_digit" else "")
                    pieces.append((code, code))
            text = "\n\n".join(markdown for markdown, _ in pieces)
            expected = "\n\n".join(converted for _, converted in pieces)
            assert md_to_whatsapp(text) == expected, f"seed {seed}: {text!r}"


class TestValidateWhatsAppFormat:
    """Tests for validate_whatsapp_format() validation."""

    def test_empty_string(self) -> None:
        valid, msg = validate_whatsapp_format("")
        assert valid
        assert msg == ""

    def test_simple_text(self) -> None:
        valid, msg = validate_whatsapp_format("*bold* text")
        assert valid
        assert msg == ""

    def test_message_size_limit(self) -> None:
        text = "a" * 5000
        valid, msg = validate_whatsapp_format(text)
        assert not valid
        assert "4KB limit" in msg

    def test_nested_formatting_star_underscore(self) -> None:
        valid, msg = validate_whatsapp_format("*_nested_*")
        assert not valid
        assert "Nested formatting" in msg

    def test_nested_formatting_underscore_star(self) -> None:
        valid, msg = validate_whatsapp_format("_*nested*_")
        assert not valid
        assert "Nested formatting" in msg

    def test_nested_formatting_strike_star(self) -> None:
        valid, msg = validate_whatsapp_format("~*nested*~")
        assert not valid
        assert "Nested formatting" in msg

    def test_non_nested_formatting(self) -> None:
        valid, msg = validate_whatsapp_format("*bold* and ~strike~")
        assert valid
        assert msg == ""
