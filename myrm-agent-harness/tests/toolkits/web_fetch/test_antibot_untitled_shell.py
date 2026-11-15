"""An untitled page that runs scripts and shows next to no text is an interstitial, not content.

WAF verification and loading screens are generated without a page template: no ``<title>``, a few scripts, one
short notice. They answer with HTTP 200 or 202, carry real markup, and used to be delivered as the page's content.
A real page, however small, names itself, so a title keeps it out of this rule.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.processing.antibot_detector import is_blocked
from tests.toolkits.web_fetch._degradation_support import (
    RICH_HTML,
    http_result,
    make_document,
    stub_fetchers,
)

URL = "http://example.com/page"
NOTICE = "JavaScript is disabled. To continue we need to verify that you are not a robot. Enable JavaScript and reload."
REASON_PREFIX = "Structural: untitled script shell"


def _page(*, title: str | None = None, scripts: int = 3, text: str = NOTICE) -> str:
    title_tag = "" if title is None else f"<title>{title}</title>"
    script_tags = "".join(f"<script>window.step{i} = {i};</script>" for i in range(scripts))
    return f"<!DOCTYPE html><html><head>{title_tag}</head><body>{script_tags}<p>{text}</p></body></html>"


@pytest.mark.parametrize("status", [200, 202])
@pytest.mark.parametrize("title", [None, "", "   "], ids=["no-title", "empty-title", "blank-title"])
def test_an_untitled_script_interstitial_is_blocked(title: str | None, status: int) -> None:
    html = _page(title=title)

    blocked, reason = is_blocked(status, html)

    assert blocked is True
    assert reason == f"{REASON_PREFIX} (3 scripts, {len(NOTICE)} chars visible, {len(html)} bytes)"


def test_a_title_makes_the_same_page_a_document() -> None:
    assert is_blocked(200, _page(title="Verification")) == (False, "")


@pytest.mark.parametrize(("scripts", "blocked"), [(0, False), (2, False), (3, True), (8, True)])
def test_three_scripts_make_a_shell(scripts: int, blocked: bool) -> None:
    assert is_blocked(200, _page(scripts=scripts))[0] is blocked


@pytest.mark.parametrize(("chars", "blocked"), [(150, True), (199, True), (200, False), (600, False)])
def test_a_paragraph_of_text_makes_it_a_page(chars: int, blocked: bool) -> None:
    assert is_blocked(200, _page(text="x" * chars))[0] is blocked


def test_a_verification_page_without_any_vendor_marker_is_blocked() -> None:
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><style>body{margin:0}</style></head><body>"
        '<script type="application/json" id="challenge">{"seed":"abc","probe_ids":[101,102]}</script>'
        "<script>window.verify=function(){return 1}</script><script>window.verify()</script>"
        '<main class="page"><section class="card"><p class="title">Security check in progress...</p>'
        '<p class="desc">The system is checking your network environment. This takes a few seconds.</p>'
        "</section></main></body></html>"
    )

    blocked, reason = is_blocked(200, html)

    assert blocked is True
    assert reason.startswith(REASON_PREFIX)


@pytest.mark.parametrize("status", [200, 202])
async def test_an_interstitial_from_l1_is_not_delivered_as_content(status: int) -> None:
    engine = FetchEngine()
    http, browser, _stealth = stub_fetchers(engine)
    pipeline = cast("MagicMock", engine._pipeline)
    browser_page = http_result(RICH_HTML)
    http.fetch.return_value = http_result(_page(), status)
    browser.fetch.return_value = browser_page
    pipeline.aprocess.return_value = make_document()

    doc, result = await engine._crawl_with_degradation(URL)

    assert doc is not None
    assert result is browser_page
    pipeline.aprocess.assert_awaited_once_with(browser_page)
    await engine.shutdown()
