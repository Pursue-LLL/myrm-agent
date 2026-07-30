"""Tests for Gmail HTML → Markdown conversion in wiki source sync."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.wiki.source_sync.html_body import html_body_to_markdown


def test_html_body_to_markdown_uses_harness_converter() -> None:
    converter = MagicMock()
    converter.handle.return_value = "# Title\n\nBody"
    with patch(
        "myrm_agent_harness.toolkits.web_fetch.html_to_markdown.HTML2Markdown",
        return_value=converter,
    ):
        result = html_body_to_markdown("<h1>Title</h1><p>Body</p>")

    assert result == "# Title\n\nBody"
    converter.update_params.assert_called_once_with(ignore_images=True)


def test_html_body_to_markdown_empty_input() -> None:
    assert html_body_to_markdown("") == ""
