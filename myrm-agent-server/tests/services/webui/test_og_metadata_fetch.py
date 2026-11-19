"""The OG preview fetch against real loopback servers: what it refuses, how far it follows, how much it reads."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from myrm_agent_harness.utils.lru_cache import LRUCache

from app.services.webui import og_metadata
from app.services.webui.og_metadata import fetch_og_metadata

_PRODUCTION_CACHE = og_metadata._og_cache  # taken before the fixtures below swap in a fresh one per test
_PAGE = '<html><head><meta property="og:title" content="Hello" /></head><body>hi</body></html>'

Route = Callable[[BaseHTTPRequestHandler], None]


class _Origin:
    """A loopback HTTP server whose routes each test fills in; ``hits`` lists every path it was asked for."""

    def __init__(self) -> None:
        self.routes: dict[str, Route] = {}
        self.hits: list[str] = []
        origin = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                origin.hits.append(self.path)
                route = origin.routes.get(self.path)
                if route is None:
                    self.send_error(404)
                    return
                route(self)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port: int = self._server.server_address[1]
        # A short poll interval keeps ``shutdown()`` from waiting half a second per test.
        threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def url(self, path: str, host: str = "127.0.0.1") -> str:
        return f"http://{host}:{self.port}{path}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def _page(body: str = _PAGE, content_type: str = "text/html; charset=utf-8") -> Route:
    def route(handler: BaseHTTPRequestHandler) -> None:
        data = body.encode()
        handler.send_response(200)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    return route


def _redirect(location: str) -> Route:
    def route(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(302)
        handler.send_header("Location", location)
        handler.send_header("Content-Length", "0")
        handler.end_headers()

    return route


def _endless(head: str) -> Route:
    """A page that starts with ``head`` and then streams filler for as long as the client listens."""

    def route(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html")
        handler.end_headers()
        try:
            handler.wfile.write(head.encode())
            while True:
                handler.wfile.write(b" " * 8192)
        except OSError:
            return

    return route


def _drip(head: str) -> Route:
    """A page that sends one byte every 50 ms, so no single read ever times out."""

    def route(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html")
        handler.end_headers()
        try:
            for byte in head.encode() * 600:
                handler.wfile.write(bytes([byte]))
                handler.wfile.flush()
                time.sleep(0.05)
        except OSError:
            return

    return route


@pytest.fixture
def origin() -> Iterator[_Origin]:
    server = _Origin()
    yield server
    server.close()


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(og_metadata, "_og_cache", LRUCache(maxsize=256, ttl=3600))


@pytest.fixture
def operator_allows_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_ALLOWED_INTERNAL_HOSTS", "127.0.0.1")


async def test_a_host_the_operator_allows_is_previewed(origin: _Origin, operator_allows_loopback: None) -> None:
    origin.routes["/page"] = _page()

    result = await fetch_og_metadata(origin.url("/page"))

    assert result["title"] == "Hello"
    assert origin.hits == ["/page"]


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "localhost", "127.1", "2130706433", "0x7f000001", "[::ffff:127.0.0.1]"],
)
async def test_an_internal_address_is_refused_before_any_request(origin: _Origin, host: str) -> None:
    origin.routes["/secret"] = _page()
    url = origin.url("/secret", host=host)

    result = await fetch_og_metadata(url)

    assert result == {"url": url}
    assert origin.hits == []


async def test_a_redirect_to_a_host_the_operator_did_not_allow_is_refused(
    origin: _Origin, operator_allows_loopback: None
) -> None:
    origin.routes["/start"] = _redirect(origin.url("/secret", host="localhost"))
    origin.routes["/secret"] = _page()
    url = origin.url("/start")

    result = await fetch_og_metadata(url)

    assert result == {"url": url}
    assert origin.hits == ["/start"]


async def test_three_redirects_are_followed(origin: _Origin, operator_allows_loopback: None) -> None:
    origin.routes["/r0"] = _redirect(origin.url("/r1"))
    origin.routes["/r1"] = _redirect(origin.url("/r2"))
    origin.routes["/r2"] = _redirect(origin.url("/page"))
    origin.routes["/page"] = _page()

    result = await fetch_og_metadata(origin.url("/r0"))

    assert result["title"] == "Hello"


async def test_a_fourth_redirect_ends_the_chain(origin: _Origin, operator_allows_loopback: None) -> None:
    for index in range(4):
        origin.routes[f"/r{index}"] = _redirect(origin.url(f"/r{index + 1}"))
    origin.routes["/r4"] = _page()
    url = origin.url("/r0")

    result = await fetch_og_metadata(url)

    assert result == {"url": url}


async def test_a_body_that_never_ends_is_cut_and_the_tags_before_the_cut_are_read(
    origin: _Origin, operator_allows_loopback: None
) -> None:
    origin.routes["/endless"] = _endless(_PAGE)

    started = time.monotonic()
    result = await fetch_og_metadata(origin.url("/endless"))

    assert result["title"] == "Hello"
    assert time.monotonic() - started < 5


async def test_tags_after_the_first_64_kib_are_ignored(origin: _Origin, operator_allows_loopback: None) -> None:
    padding = "<!--" + "x" * (64 * 1024) + "-->"
    origin.routes["/late"] = _page(f'<html><head>{padding}<meta property="og:title" content="Late" /></head></html>')
    url = origin.url("/late")

    result = await fetch_og_metadata(url)

    assert result == {"url": url}


async def test_a_page_that_drips_bytes_is_cut_by_the_deadline(
    origin: _Origin, operator_allows_loopback: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(og_metadata, "_DEADLINE_SECONDS", 0.5)
    origin.routes["/drip"] = _drip(_PAGE)
    url = origin.url("/drip")

    started = time.monotonic()
    result = await fetch_og_metadata(url)

    assert result == {"url": url}
    assert time.monotonic() - started < 3


@pytest.mark.parametrize("route", [_page('{"a": 1}', "application/json"), None])
async def test_a_page_that_is_not_html_or_is_missing_has_no_preview(
    origin: _Origin, operator_allows_loopback: None, route: Route | None
) -> None:
    if route is not None:
        origin.routes["/page"] = route
    url = origin.url("/page")

    result = await fetch_og_metadata(url)

    assert result == {"url": url}


async def test_a_second_request_for_a_url_is_served_from_the_cache(origin: _Origin, operator_allows_loopback: None) -> None:
    origin.routes["/page"] = _page()
    url = origin.url("/page")

    first = await fetch_og_metadata(url)
    second = await fetch_og_metadata(url)

    assert first == second
    assert origin.hits == ["/page"]


async def test_the_cache_drops_the_page_used_least_recently(
    origin: _Origin, operator_allows_loopback: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(og_metadata, "_og_cache", LRUCache(maxsize=2, ttl=3600))
    for name in ("a", "b", "c"):
        origin.routes[f"/{name}"] = _page()
    urls: dict[str, str] = {name: origin.url(f"/{name}") for name in ("a", "b", "c")}

    for name in ("a", "b", "a", "c", "a", "b"):
        await fetch_og_metadata(urls[name])

    assert origin.hits == ["/a", "/b", "/c", "/b"]


def test_the_production_cache_holds_256_pages_for_an_hour() -> None:
    assert (_PRODUCTION_CACHE.maxsize, _PRODUCTION_CACHE.ttl) == (256, 3600)
