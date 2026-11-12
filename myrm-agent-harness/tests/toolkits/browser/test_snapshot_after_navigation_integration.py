"""Real-Chromium proof that a snapshot describes the page the tab shows after the page itself navigated.

A link click, a form submit or a script redirect loads a new document without any call to `navigate()`, so nothing
resets the snapshot cache. The observer that tells "nothing changed" lives inside the page and is gone with the old
document: the next snapshot used to answer "No DOM changes detected" for a page that was no longer there. Run with:
`pytest -m integration tests/toolkits/browser/test_snapshot_after_navigation_integration.py`.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.browser.session.snapshot_result import SnapshotResult
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._local_browser_session import local_session
from tests.toolkits.browser._redirect_servers import page, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_ROUTES = {
    "/first": page("<h1>First</h1><a href='/second'>Next</a>"),
    "/second": page("<h1>Second</h1><button>Confirm</button>"),
}


def _ref_named(snapshot: SnapshotResult, name: str) -> str:
    return next(ref for ref, info in snapshot.refs.items() if info.name == name)


def _names(snapshot: SnapshotResult) -> set[str]:
    return {info.name for info in snapshot.refs.values()}


async def test_a_snapshot_after_a_click_that_loads_another_page_describes_that_page() -> None:
    with serve(_ROUTES) as site:
        async with local_session() as session:
            await session.navigate(site.url("/first"))
            first = await session.snapshot()
            assert "Next" in _names(first)

            await session.interact("click", _ref_named(first, "Next"))
            await session.get_active_page().wait_for_url(site.url("/second"))
            second = await session.snapshot()

            assert "Confirm" in _names(second)
            assert "Next" not in _names(second)
            assert "No DOM changes" not in second.aria_tree


async def test_a_snapshot_after_going_back_describes_the_page_the_tab_returned_to() -> None:
    with serve(_ROUTES) as site:
        async with local_session() as session:
            await session.navigate(site.url("/first"))
            await session.interact("click", _ref_named(await session.snapshot(), "Next"))
            await session.get_active_page().wait_for_url(site.url("/second"))
            assert "Confirm" in _names(await session.snapshot())

            await session.get_active_page().go_back()
            await session.get_active_page().wait_for_url(site.url("/first"))
            after_back = _names(await session.snapshot())

            assert "Next" in after_back
            assert "Confirm" not in after_back
