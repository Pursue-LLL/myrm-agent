"""A page served with 403 or a server error is an error page, whatever its size or markup.

Error and challenge pages carry ordinary page chrome and inline bundles, so the size and structure gates wave
them through; the status code is the signal that cannot be diluted. The other 4xx answers (404, 410, ...) are
the origin's final word on the request: another tier cannot change them, so the content rules judge those.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.engine.types import DEGRADABLE_4XX
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetcherType
from myrm_agent_harness.toolkits.web_fetch.processing.antibot_detector import is_blocked
from tests.toolkits.web_fetch._degradation_support import (
    RICH_HTML,
    http_result,
    make_document,
    start_on,
    stub_fetchers,
)

URL = "http://example.com/page"
SERVER_ERRORS = [500, 502, 504, 520, 521, 522, 526, 530, 599]
PAGE_SIZES = [
    pytest.param(0, id="small"),
    pytest.param(30_000, id="medium"),
    pytest.param(300_000, id="large"),
]


def _content_page(bundle_bytes: int) -> str:
    """A page every content rule accepts: titled, twelve real paragraphs, and an inline bundle of the given size."""
    paragraphs = "".join(
        f"<p>Paragraph {i} explains one topic of the page in a full sentence of ordinary prose.</p>" for i in range(12)
    )
    bundle = f"<script>{'x' * bundle_bytes}</script>" if bundle_bytes else ""
    return f"<!DOCTYPE html><html><head><title>Service notice</title>{bundle}</head><body><main>{paragraphs}</main></body></html>"


@pytest.mark.parametrize("bundle_bytes", PAGE_SIZES)
@pytest.mark.parametrize("status", [200, 202, 301])
def test_the_same_page_passes_under_a_success_status(status: int, bundle_bytes: int) -> None:
    blocked, reason = is_blocked(status, _content_page(bundle_bytes))

    assert (blocked, reason) == (False, "")


@pytest.mark.parametrize("bundle_bytes", PAGE_SIZES)
@pytest.mark.parametrize("status", [403, *SERVER_ERRORS])
def test_a_page_with_a_refusal_status_is_blocked_whatever_its_size(status: int, bundle_bytes: int) -> None:
    html = _content_page(bundle_bytes)

    blocked, reason = is_blocked(status, html)

    assert blocked is True
    assert reason == f"HTTP {status} with HTML content ({len(html)} bytes)"


@pytest.mark.parametrize("status", sorted(DEGRADABLE_4XX))
def test_every_client_error_the_engine_degrades_on_is_blocked(status: int) -> None:
    assert is_blocked(status, _content_page(30_000))[0] is True


@pytest.mark.parametrize("status", [404, 410, 499])
def test_other_client_errors_stay_with_the_content_rules(status: int) -> None:
    assert status not in DEGRADABLE_4XX
    assert is_blocked(status, _content_page(30_000)) == (False, "")


def test_a_server_error_page_keeps_the_marker_reason_it_matched() -> None:
    html = _content_page(30_000).replace("<main>", "<main><h1>Access Denied</h1>")

    blocked, reason = is_blocked(500, html)

    assert blocked is True
    assert reason == f"Access Denied on short page (HTTP 500, {len(html)} bytes)"


@pytest.mark.parametrize("status", [500, 502])
def test_a_near_empty_server_error_is_blocked(status: int) -> None:
    assert is_blocked(status, "<html></html>") == (True, f"HTTP {status} with near-empty response (13 bytes)")


@pytest.mark.parametrize(
    "body",
    ['{"error": "internal", "detail": "database unavailable"}', '<?xml version="1.0"?><error>bad gateway</error>'],
    ids=["json", "xml"],
)
def test_a_server_error_with_a_data_body_is_not_judged_as_a_page(body: str) -> None:
    assert is_blocked(500, body) == (False, "")


async def test_a_server_error_page_from_l1_is_not_delivered_as_content() -> None:
    engine = FetchEngine()
    http, browser, _stealth = stub_fetchers(engine)
    pipeline = cast("MagicMock", engine._pipeline)
    browser_page = http_result(RICH_HTML)
    http.fetch.return_value = http_result(_content_page(30_000), 521)
    browser.fetch.return_value = browser_page
    pipeline.aprocess.return_value = make_document()

    doc, result = await engine._crawl_with_degradation(URL)

    assert doc is not None
    assert result is browser_page
    pipeline.aprocess.assert_awaited_once_with(browser_page)
    await engine.shutdown()


async def test_a_server_error_page_that_every_tier_returns_is_never_processed() -> None:
    engine = FetchEngine()
    http, browser, stealth = stub_fetchers(engine)
    start_on(engine, FetcherType.HTTP)
    for fetcher in (http, browser, stealth):
        fetcher.fetch.return_value = http_result(_content_page(30_000), 500)

    doc, _result = await engine._crawl_with_degradation(URL, allow_escalation=False)

    assert doc is None
    cast("MagicMock", engine._pipeline).aprocess.assert_not_awaited()
    await engine.shutdown()
