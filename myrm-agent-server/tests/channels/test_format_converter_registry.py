"""Unit tests for FormatConverterRegistry."""

from __future__ import annotations

import pytest

from app.channels.rendering.converter_registry import (
    FormatConverterRegistry,
)


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    """Clear registry before each test, restore Slack converter after."""
    saved = dict(FormatConverterRegistry._converters) if hasattr(FormatConverterRegistry, "_converters") else {}
    FormatConverterRegistry.clear()
    yield
    FormatConverterRegistry.clear()
    for key, fn in saved.items():
        FormatConverterRegistry._converters[key] = fn


class TestFormatConverterRegistry:
    """Tests for FormatConverterRegistry."""

    def test_register_and_convert(self) -> None:
        def upper_converter(text: str) -> str:
            return text.upper()

        FormatConverterRegistry.register("markdown", "test", upper_converter)
        result = FormatConverterRegistry.convert("hello", "markdown", "test")
        assert result == "HELLO"

    def test_convert_without_registered_converter(self) -> None:
        result = FormatConverterRegistry.convert("hello", "foo", "bar")
        assert result == "hello"  # Returns original

    def test_convert_empty_string(self) -> None:
        FormatConverterRegistry.register("markdown", "test", lambda t: "CONVERTED")
        result = FormatConverterRegistry.convert("", "markdown", "test")
        assert result == ""

    def test_convert_case_insensitive(self) -> None:
        FormatConverterRegistry.register("Markdown", "Test", lambda t: t.upper())
        result = FormatConverterRegistry.convert("hello", "MARKDOWN", "TEST")
        assert result == "HELLO"

    def test_convert_error_returns_original(self) -> None:
        def failing_converter(_: str) -> str:
            raise ValueError("Conversion failed")

        FormatConverterRegistry.register("markdown", "test", failing_converter)
        result = FormatConverterRegistry.convert("hello", "markdown", "test")
        assert result == "hello"  # Fallback to original

    def test_auto_fallback_first_success(self) -> None:
        FormatConverterRegistry.register("markdown", "target", lambda t: f"MD:{t}")
        result = FormatConverterRegistry.auto_fallback(
            "text", "target", fallback_chain=["rich", "markdown", "plaintext"]
        )
        assert result == "MD:text"

    def test_auto_fallback_skip_failed(self) -> None:
        FormatConverterRegistry.register("rich", "target", lambda _: _ + " (rich)")
        FormatConverterRegistry.register("markdown", "target", lambda t: t + " (md)")

        result = FormatConverterRegistry.auto_fallback("text", "target", fallback_chain=["markdown", "plaintext"])
        assert result == "text (md)"

    def test_auto_fallback_all_failed(self) -> None:
        result = FormatConverterRegistry.auto_fallback("text", "target", fallback_chain=["foo", "bar"])
        assert result == "text"  # Returns original

    def test_auto_fallback_default_chain(self) -> None:
        FormatConverterRegistry.register("markdown", "target", lambda t: f"MD:{t}")
        result = FormatConverterRegistry.auto_fallback("text", "target")
        assert result == "MD:text"

    def test_list_converters(self) -> None:
        FormatConverterRegistry.register("markdown", "html", lambda t: t)
        FormatConverterRegistry.register("html", "plaintext", lambda t: t)

        converters = FormatConverterRegistry.list_converters()
        assert ("markdown", "html") in converters
        assert ("html", "plaintext") in converters
        assert len(converters) == 2

    def test_replace_existing_converter(self) -> None:
        FormatConverterRegistry.register("markdown", "test", lambda t: "OLD")
        FormatConverterRegistry.register("markdown", "test", lambda t: "NEW")

        result = FormatConverterRegistry.convert("text", "markdown", "test")
        assert result == "NEW"
