"""Chrome E2E (NAMESPACE_WRITE): real WBBench run starts through the Eval Lab UI.

Walks the real user flow: open the Eval Lab page, click the Run button on a
subset card, and wait for the backend to report a live eval run through the SSE
status stream. The Run flow navigates to the "Eval Report" tab, so the running
state is asserted through the header Stop button plus the report progress text,
not the sources grid. The test then aborts so the shared stack is never left
running.

The ``office`` subset is used because it is already downloaded locally (the
``web`` subset download is rate-limited by HuggingFace in this environment, so a
run would fail before the running state could be observed).
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
    click_subset_run_js,
    restore_eval_lab_route,
)

# A live WBBench run must surface through the header Stop button and the report
# tab progress text ("Eval task in progress" / "Downloading"). The sources tab
# is unmounted while the run is in flight, so grid buttons are not a probe.
_RUN_INFLIGHT_JS = """(() => {
  const body = document.body?.innerText || document.body?.textContent || '';
  const stopBtn = Array.from(document.querySelectorAll('button')).find(
    (b) => /Stop|停止/.test((b.textContent || '').trim()),
  );
  const runningText = /Eval task in progress|Downloading/i.test(body);
  return {
    ready: !!stopBtn && runningText,
    hasStop: !!stopBtn,
    runningText,
    bodyLength: body.length,
  };
})()"""

# Clicks the Stop button that appears in the page header while a run is in flight.
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

# After abort the run flag clears: the Stop button disappears and the report tab
# stops showing in-progress text.
_RUN_CLEARED_JS = """(() => {
  const body = document.body?.innerText || document.body?.textContent || '';
  const stopBtn = Array.from(document.querySelectorAll('button')).find(
    (b) => /Stop|停止/.test((b.textContent || '').trim()),
  );
  const runningText = /Eval task in progress|Downloading/i.test(body);
  return {
    ready: !stopBtn && !runningText,
    hasStop: !!stopBtn,
    runningText,
    bodyLength: body.length,
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

        clicked = client.evaluate(page, click_subset_run_js("WBBench Office"))
        assert clicked.get("ok") is True, clicked

        # The run must surface the header Stop button and report progress text
        # immediately after the frontend sets the running flag.
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
