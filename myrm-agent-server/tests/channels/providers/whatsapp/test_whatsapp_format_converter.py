"""Unit tests for WhatsApp format converter."""

from __future__ import annotations

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
