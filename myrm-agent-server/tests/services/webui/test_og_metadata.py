"""Tests for Open Graph metadata fetcher."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import httpx
import pytest
from myrm_agent_harness.utils.lru_cache import LRUCache

from app.services.webui import og_metadata
from app.services.webui.og_metadata import _parse_og_tags

# Public IP literals: the SSRF guard accepts them without a DNS lookup, so these tests never touch the network.
PUBLIC_HOST = "http://8.8.8.8"
OTHER_PUBLIC_HOST = "http://1.1.1.1"
METADATA_URL = "http://169.254.169.254/latest/meta-data/"


def _html_page(request: httpx.Request, title: str, *, body: str = "") -> httpx.Response:
    """A 200 HTML response for ``request`` whose document is ``<title>`` followed by ``body``."""
    return httpx.Response(200, headers={"content-type": "text/html"}, text=f"<title>{title}</title>{body}", request=request)


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
        """Replace the SSRF-guarded download with an in-process page server; returns the URLs it was asked for."""
        requested: list[str] = []

        async def fake_secure_get(url: str, **_: object) -> httpx.Response:
            requested.append(url)
            request = httpx.Request("GET", url)
            return _html_page(request, request.url.path)

        monkeypatch.setattr(og_metadata, "secure_get", fake_secure_get)
        return requested

    async def test_repeat_fetch_is_served_from_the_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        requested = self._serve_pages(monkeypatch)

        first = await og_metadata.fetch_og_metadata("https://example.com/a")
        second = await og_metadata.fetch_og_metadata("https://example.com/a")

        assert first == second == {"title": "/a", "url": "https://example.com/a"}
        assert requested == ["https://example.com/a"]

    async def test_cache_drops_the_least_recently_used_page_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        requested = self._serve_pages(monkeypatch)
        monkeypatch.setattr(og_metadata, "_og_cache", LRUCache(maxsize=2, ttl=3600))
        page_a, page_b, page_c = (f"https://example.com/{name}" for name in "abc")

        await og_metadata.fetch_og_metadata(page_a)
        await og_metadata.fetch_og_metadata(page_b)
        await og_metadata.fetch_og_metadata(page_a)  # a is now newer than b
        await og_metadata.fetch_og_metadata(page_c)  # the cache is full: b goes

        requested.clear()
        await og_metadata.fetch_og_metadata(page_a)
        await og_metadata.fetch_og_metadata(page_b)
        assert requested == [page_b]


class TestSsrfShield:
    """The download runs through the real SSRF shield; only the network wire is faked."""

    @pytest.fixture(autouse=True)
    def _shield_on_with_empty_cache(self, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
        monkeypatch.setenv("MYRM_ENABLE_SSRF_SHIELD", "true")
        monkeypatch.delenv("MYRM_ALLOWED_INTERNAL_HOSTS", raising=False)
        og_metadata._og_cache.clear()
        yield
        og_metadata._og_cache.clear()

    @staticmethod
    def _fake_wire(monkeypatch: pytest.MonkeyPatch, respond: Callable[[httpx.Request], httpx.Response]) -> list[httpx.Request]:
        """Answer every request at the transport, below the client's own redirect handling.

        Returns the requests that actually reached the wire.
        """
        sent: list[httpx.Request] = []

        async def fake_transport(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
            sent.append(request)
            return respond(request)

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_transport)
        return sent

    @pytest.mark.parametrize(
        "internal_url",
        ["http://127.0.0.1:8080/admin", METADATA_URL, "http://10.0.0.5/", "http://[::1]/"],
    )
    async def test_internal_addresses_are_never_requested(self, monkeypatch: pytest.MonkeyPatch, internal_url: str) -> None:
        sent = self._fake_wire(monkeypatch, lambda request: _html_page(request, "internal secret"))

        assert await og_metadata.fetch_og_metadata(internal_url) == {"url": internal_url}
        assert sent == []

    async def test_redirect_into_the_internal_network_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        start = f"{PUBLIC_HOST}/start"
        sent = self._fake_wire(
            monkeypatch,
            lambda request: httpx.Response(302, headers={"location": METADATA_URL}, request=request),
        )

        assert await og_metadata.fetch_og_metadata(start) == {"url": start}
        assert [str(request.url) for request in sent] == [start]

    async def test_redirect_between_public_hosts_is_followed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        start, final = f"{PUBLIC_HOST}/start", f"{OTHER_PUBLIC_HOST}/final"

        def respond(request: httpx.Request) -> httpx.Response:
            if str(request.url) == start:
                return httpx.Response(302, headers={"location": final}, request=request)
            return _html_page(request, "Final")

        sent = self._fake_wire(monkeypatch, respond)

        assert await og_metadata.fetch_og_metadata(start) == {"title": "Final", "url": start}
        assert [str(request.url) for request in sent] == [start, final]
        assert {request.headers["user-agent"] for request in sent} == {og_metadata._USER_AGENT}

    async def test_only_the_first_window_of_a_page_is_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        page = f"{PUBLIC_HOST}/long"
        late_tag = '<meta property="og:description" content="Late" />'
        self._fake_wire(
            monkeypatch,
            lambda request: _html_page(request, "Early", body=" " * og_metadata._MAX_BODY_BYTES + late_tag),
        )

        assert await og_metadata.fetch_og_metadata(page) == {"title": "Early", "url": page}

    async def test_non_html_response_yields_no_preview(self, monkeypatch: pytest.MonkeyPatch) -> None:
        page = f"{PUBLIC_HOST}/data.json"
        self._fake_wire(
            monkeypatch,
            lambda request: httpx.Response(200, headers={"content-type": "application/json"}, text="{}", request=request),
        )

        assert await og_metadata.fetch_og_metadata(page) == {"url": page}
