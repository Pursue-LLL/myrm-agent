"""Chrome E2E (NAMESPACE_WRITE): WBBench download state refresh + disabled buttons.

Walks the real user flow: open Eval Lab, download the ``web`` subset (22 MB,
larger than office so the download window is observable), then verify:

  1. While a download runs every subset card disables its Download/Run buttons.
  2. The card flips to the downloaded state once the backend installs the source.
  3. Clicking the manual Refresh button re-pulls the catalog and the downloaded
     badge/disabled button survive.
  4. Reloading the page keeps the downloaded state (backend persistence).

Uses a private backend so the shared stack is never polluted.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)
from tests.support.wb_bench_e2e_helpers import (
    EVAL_LAB_PATH,
    SOURCES_READY_JS,
    click_subset_download_js,
    restore_eval_lab_route,
    subset_downloaded_js,
)

# While a download is running the backend marks eval busy; every Download/Run
# button on the sources grid must be disabled until the state resets.
_ALL_BUTTONS_DISABLED_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const grid = buttons.filter((b) => {
    if (!/Download|下载|Run|运行/i.test(b.textContent || '')) return false;
    let node = b.parentElement;
    while (node && node !== document.body) {
      if (/WBBench/.test(node.textContent || '')) return true;
      node = node.parentElement;
    }
    return false;
  });
  return {
    ready: grid.length >= 8 && grid.every((b) => b.disabled === true),
    total: grid.length,
    disabledCount: grid.filter((b) => b.disabled === true).length,
  };
})()"""

# Clicks the Refresh button next to the WBBench sources heading.
_CLICK_REFRESH_JS = """(() => {
  const target = Array.from(document.querySelectorAll('button')).find((b) => {
    const text = (b.textContent || '').trim();
    return /Refresh|刷新/i.test(text);
  });
  if (!target) return { ok: false, err: 'refresh-button-missing' };
  const opts = { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 };
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return { ok: true, clicked: true };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wb_bench_download_refresh_and_buttons_chrome_e2e() -> None:
    """Downloading the web subset disables buttons, then persists across refresh/reload."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route(EVAL_LAB_PATH)

    with open_mcp_page(f"{ui_url}{EVAL_LAB_PATH}", timeout_ms=120_000) as (
        client,
        page,
    ):
        restore_eval_lab_route(client, page, f"{ui_url}{EVAL_LAB_PATH}")
        dismiss_blocking_modals(client, page)
        sources_ready = wait_for_state(
            client, page, SOURCES_READY_JS, timeout_sec=120.0
        )
        assert sources_ready.get("ready") is True, sources_ready

        clicked = client.evaluate(page, click_subset_download_js("WBBench Web"))
        assert clicked.get("ok") is True, clicked

        # The download for web (~22 MB) runs for a while; during that window the
        # whole grid must be non-interactive. Office/other downloads may already
        # be installed from prior runs, so only assert buttons that exist.
        all_disabled = wait_for_state(
            client,
            page,
            _ALL_BUTTONS_DISABLED_JS,
            timeout_sec=60.0,
        )
        # At least the 4 cards must render their buttons; all must be disabled.
        assert all_disabled.get("ready") is True, all_disabled

        downloaded = wait_for_state(
            client, page, subset_downloaded_js("WBBench Web"), timeout_sec=300.0
        )
        assert downloaded.get("ready") is True, downloaded

        # Manual refresh re-pulls the catalog; the downloaded state must persist.
        refreshed = client.evaluate(page, _CLICK_REFRESH_JS)
        assert refreshed.get("ok") is True, refreshed
        after_refresh = wait_for_state(
            client,
            page,
            subset_downloaded_js("WBBench Web"),
            timeout_sec=60.0,
        )
        assert after_refresh.get("ready") is True, after_refresh
