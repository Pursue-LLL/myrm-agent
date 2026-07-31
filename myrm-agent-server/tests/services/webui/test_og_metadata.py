"""Tests for Open Graph metadata fetcher."""

from __future__ import annotations

from app.services.webui.og_metadata import _parse_og_tags


class TestParseOgTags:
    """Unit tests for OG tag parsing from HTML."""

    def test_basic_og_tags(self) -> None:
        html = '''
        <html><head>
        <meta property="og:title" content="Test Title" />
        <meta property="og:description" content="Test Description" />
        <meta property="og:image" content="https://example.com/img.jpg" />
        <meta property="og:site_name" content="Example" />
        </head></html>
        '''
        result = _parse_og_tags(html, "https://example.com")
        assert result["title"] == "Test Title"
        assert result["description"] == "Test Description"
        assert result["image"] == "https://example.com/img.jpg"
        assert result["site_name"] == "Example"

    def test_fallback_to_title_tag(self) -> None:
        html = '<html><head><title>Fallback Title</title></head></html>'
        result = _parse_og_tags(html, "https://example.com")
        assert result["title"] == "Fallback Title"

    def test_og_title_takes_precedence(self) -> None:
        html = '''
        <html><head>
        <title>HTML Title</title>
        <meta property="og:title" content="OG Title" />
        </head></html>
        '''
        result = _parse_og_tags(html, "https://example.com")
        assert result["title"] == "OG Title"

    def test_favicon_absolute_url(self) -> None:
        html = '<link rel="icon" href="https://example.com/favicon.ico" />'
        result = _parse_og_tags(html, "https://example.com")
        assert result.get("favicon") == "https://example.com/favicon.ico"

    def test_favicon_relative_url(self) -> None:
        html = '<link rel="icon" href="/favicon.ico" />'
        result = _parse_og_tags(html, "https://example.com/page")
        assert result.get("favicon") == "https://example.com/favicon.ico"

    def test_favicon_protocol_relative(self) -> None:
        html = '<link rel="icon" href="//cdn.example.com/icon.png" />'
        result = _parse_og_tags(html, "https://example.com")
        assert result.get("favicon") == "https://cdn.example.com/icon.png"

    def test_empty_html(self) -> None:
        result = _parse_og_tags("", "https://example.com")
        assert result == {"url": "https://example.com"}

    def test_html_entity_decoding(self) -> None:
        html = '<meta property="og:title" content="Tom &amp; Jerry" />'
        result = _parse_og_tags(html, "https://example.com")
        assert result["title"] == "Tom & Jerry"

    def test_url_always_present(self) -> None:
        result = _parse_og_tags("<html></html>", "https://example.com")
        assert result["url"] == "https://example.com"

    def test_reversed_attribute_order(self) -> None:
        """OG tags with content before property."""
        html = '<meta content="Reversed Title" property="og:title" />'
        result = _parse_og_tags(html, "https://example.com")
        assert result["title"] == "Reversed Title"

    def test_apple_touch_icon(self) -> None:
        html = '<link rel="apple-touch-icon" href="/apple-icon.png" />'
        result = _parse_og_tags(html, "https://example.com")
        assert result.get("favicon") == "https://example.com/apple-icon.png"

    def test_shortcut_icon(self) -> None:
        html = '<link rel="shortcut icon" href="/shortcut.ico" />'
        result = _parse_og_tags(html, "https://example.com")
        assert result.get("favicon") == "https://example.com/shortcut.ico"
