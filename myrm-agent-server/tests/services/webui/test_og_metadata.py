"""Tests for Open Graph metadata fetcher."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from app.services.webui import og_metadata
from app.services.webui.og_metadata import _parse_og_tags


class TestParseOgTags:
    """Unit tests for OG tag parsing from HTML."""

    def test_basic_og_tags(self) -> None:
        html = """
        <html><head>
        <meta property="og:title" content="Test Title" />
        <meta property="og:description" content="Test Description" />
        <meta property="og:image" content="https://example.com/img.jpg" />
        <meta property="og:site_name" content="Example" />
        </head></html>
        """
        result = _parse_og_tags(html, "https://example.com")
        assert result["title"] == "Test Title"
        assert result["description"] == "Test Description"
        assert result["image"] == "https://example.com/img.jpg"
        assert result["site_name"] == "Example"

    def test_fallback_to_title_tag(self) -> None:
        html = "<html><head><title>Fallback Title</title></head></html>"
        result = _parse_og_tags(html, "https://example.com")
        assert result["title"] == "Fallback Title"

    def test_og_title_takes_precedence(self) -> None:
        html = """
        <html><head>
        <title>HTML Title</title>
        <meta property="og:title" content="OG Title" />
        </head></html>
        """
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


class TestFetchCache:
    """fetch_og_metadata remembers the pages it already fetched, up to a fixed number, newest use last."""

    @pytest.fixture(autouse=True)
    def _empty_cache(self) -> Iterator[None]:
        og_metadata._og_cache.clear()
        yield
        og_metadata._og_cache.clear()

    @staticmethod
    def _serve_pages(monkeypatch: pytest.MonkeyPatch) -> list[str]:
        """Point the fetcher's HTTP client at an in-process page server; returns the URLs it was asked for."""
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, headers={"content-type": "text/html"}, text=f"<title>{request.url.path}</title>")

        real_client = httpx.AsyncClient
        monkeypatch.setattr(
            og_metadata.httpx,
            "AsyncClient",
            lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
        )
        return requested

    async def test_repeat_fetch_is_served_from_the_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        requested = self._serve_pages(monkeypatch)

        first = await og_metadata.fetch_og_metadata("https://example.com/a")
        second = await og_metadata.fetch_og_metadata("https://example.com/a")

        assert first == second == {"title": "/a", "url": "https://example.com/a"}
        assert requested == ["https://example.com/a"]

    async def test_cache_drops_the_least_recently_used_page_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        requested = self._serve_pages(monkeypatch)
        monkeypatch.setattr(og_metadata, "_CACHE_MAX_ENTRIES", 2)
        page_a, page_b, page_c = (f"https://example.com/{name}" for name in "abc")

        await og_metadata.fetch_og_metadata(page_a)
        await og_metadata.fetch_og_metadata(page_b)
        await og_metadata.fetch_og_metadata(page_a)  # a is now newer than b
        await og_metadata.fetch_og_metadata(page_c)  # the cache is full: b goes

        assert list(og_metadata._og_cache) == [page_a, page_c]
        requested.clear()
        await og_metadata.fetch_og_metadata(page_a)
        await og_metadata.fetch_og_metadata(page_b)
        assert requested == [page_b]
