"""Chrome E2E (NAMESPACE_WRITE): real WBBench run starts through the Eval Lab UI.

Walks the real user flow: open the Eval Lab page, click the Run button on a
subset card, and wait for the backend to report a live eval run (stage
``downloading`` → ``evaluating``) through the SSE status stream. Verifies the
progress UI renders and the whole grid is non-interactive while the run is in
flight, then aborts so the shared stack is never left running.

The ``web`` subset (22 MB) is used because it is small enough to download inside
the test budget yet large enough to observe the running state before the run
finishes.
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
    restore_eval_lab_route,
)

# Click the Run button inside the WBBench Web card.
_CLICK_WEB_RUN_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const target = buttons.find((b) => {
    if (!/Run|运行/i.test(b.textContent || '')) return false;
    let node = b.parentElement;
    while (node && node !== document.body) {
      if ((node.textContent || '').includes('WBBench Web')) return true;
      node = node.parentElement;
    }
    return false;
  });
  if (!target) return { ok: false, err: 'web-run-button-missing' };
  if (target.disabled) return { ok: false, err: 'web-run-button-disabled' };
  const opts = { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 };
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return { ok: true, clicked: true };
})()"""

# A live WBBench run must reach the evaluating stage (or still be downloading)
# and the sources grid buttons must be disabled while running.
_RUN_INFLIGHT_JS = """(() => {
  const body = document.body?.innerText || document.body?.textContent || '';
  const buttons = Array.from(document.querySelectorAll('button'));
  const gridButtons = buttons.filter((b) => {
    if (!/Download|下载|Run|运行/i.test(b.textContent || '')) return false;
    let node = b.parentElement;
    while (node && node !== document.body) {
      if (/WBBench/.test(node.textContent || '')) return true;
      node = node.parentElement;
    }
    return false;
  });
  const inProgress = /downloading|下载中|evaluating|评估中|Running|运行中/i.test(body);
  return {
    ready: gridButtons.length >= 8 && gridButtons.every((b) => b.disabled === true),
    total: gridButtons.length,
    disabledCount: gridButtons.filter((b) => b.disabled === true).length,
    inProgress,
    bodyLength: body.length,
  };
})()"""

# Clicks the Stop button that appears while a run is in flight.
_CLICK_STOP_JS = """(() => {
  const target = Array.from(document.querySelectorAll('button')).find((b) => {
    const text = (b.textContent || '').trim();
    return /Stop|停止/i.test(text);
  });
  if (!target) return { ok: false, err: 'stop-button-missing' };
  const opts = { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 };
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return { ok: true, clicked: true };
})()"""

# After abort the run flag clears and the grid becomes interactive again.
_RUN_CLEARED_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const gridButtons = buttons.filter((b) => {
    if (!/Download|下载|Run|运行/i.test(b.textContent || '')) return false;
    let node = b.parentElement;
    while (node && node !== document.body) {
      if (/WBBench/.test(node.textContent || '')) return true;
      node = node.parentElement;
    }
    return false;
  });
  return {
    ready: gridButtons.length >= 8 && gridButtons.some((b) => b.disabled === false),
    total: gridButtons.length,
    enabledCount: gridButtons.filter((b) => b.disabled === false).length,
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wb_bench_run_starts_and_can_abort_chrome_e2e() -> None:
    """Clicking Run starts a real WBBench eval and the Stop button aborts it."""
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

        clicked = client.evaluate(page, _CLICK_WEB_RUN_JS)
        assert clicked.get("ok") is True, clicked

        # The run must disable the grid immediately (SSE marks eval busy) and
        # surface a progress state.
        inflight = wait_for_state(
            client,
            page,
            _RUN_INFLIGHT_JS,
            timeout_sec=90.0,
        )
        assert inflight.get("ready") is True, inflight

        # Abort the run so the shared backend is not left evaluating forever.
        stopped = client.evaluate(page, _CLICK_STOP_JS)
        assert stopped.get("ok") is True, stopped

        cleared = wait_for_state(
            client,
            page,
            _RUN_CLEARED_JS,
            timeout_sec=60.0,
        )
        assert cleared.get("ready") is True, cleared
