"""Integration tests for blocking-modal detection in browser snapshots.

Uses real Patchright/Chromium. Run with: pytest -m integration

A snapshot marks interactive elements outside the active modal as ``[blocked]`` (no ref). Only a genuine
overlay layer may do that: pages that merely fill the viewport (long articles, full-height app roots) must
keep every field reachable, and fields inside a real dialog must stay reachable even when they are named
by placeholder or label rather than inner text.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.browser.pool import ContextType, GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.session import BrowserSession

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.asyncio]

_TALL_PAGE = """
<!DOCTYPE html>
<html><body>
  <button>Go</button>
  <input type="text" placeholder="Search">
  <div style="height: 3000px"></div>
</body></html>
"""

_FULL_HEIGHT_APP_ROOT = """
<!DOCTYPE html>
<html><body>
  <div id="root" style="min-height: 100vh">
    <button>Go</button>
    <input type="text" placeholder="Search">
  </div>
</body></html>
"""

_DIALOG_OVER_PAGE = """
<!DOCTYPE html>
<html><body>
  <button>Background action</button>
  <div style="position: fixed; inset: 0; z-index: 10; background: rgba(0, 0, 0, 0.5)">
    <div role="dialog" aria-modal="true" style="margin: 80px auto; width: 320px; background: white">
      <label for="code">Invite code</label>
      <input id="code" type="text">
      <input type="email" placeholder="Email">
      <button>Confirm</button>
    </div>
  </div>
</body></html>
"""


@pytest.fixture
async def browser_pool() -> GlobalBrowserPool:
    pool = GlobalBrowserPool(max_browsers=1)
    await pool.warmup(browsers=1, pages_per_context=1)
    yield pool
    await pool.shutdown()


@pytest.fixture
async def browser_session(browser_pool: GlobalBrowserPool) -> BrowserSession:
    session = BrowserSession(browser_pool, ContextType.AGENT)
    yield session
    await session.close()


async def _snapshot_tree(session: BrowserSession, html: str) -> str:
    await session.new_tab("about:blank")
    await session.get_active_page().set_content(html)
    return (await session.snapshot(diff=False)).aria_tree


@pytest.mark.parametrize("html", [_TALL_PAGE, _FULL_HEIGHT_APP_ROOT], ids=["tall_page", "full_height_app_root"])
async def test_in_flow_page_never_blocks_its_fields(browser_session: BrowserSession, html: str) -> None:
    tree = await _snapshot_tree(browser_session, html)

    assert "[blocked]" not in tree
    assert 'textbox "Search" [ref=' in tree


async def test_dialog_keeps_its_own_fields_reachable_and_blocks_the_page_behind(
    browser_session: BrowserSession,
) -> None:
    tree = await _snapshot_tree(browser_session, _DIALOG_OVER_PAGE)

    assert '[blocked] button "Background action"' in tree
    assert 'textbox "Invite code" [ref=' in tree
    assert 'textbox "Email" [ref=' in tree
    assert 'button "Confirm" [ref=' in tree
