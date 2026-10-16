"""Chrome E2E: undoing a skill save that was already undone elsewhere says so once and leaves the skill alone."""

from __future__ import annotations

import re
import time
from collections import Counter

import pytest

from tests.e2e.test_memory_keyword_recall_live_chrome_e2e import _attach_probe_js
from tests.e2e.test_skill_manage_undo_rollback_chrome_e2e import (
    _ATTACH_TIMEOUT_SEC,
    _PAGE_TIMEOUT_MS,
    _WATCH_ROLLBACK_JS,
    _fetch_skill_md,
    _seed_chat_with_batch,
    _seed_mutation_batch,
    confirm_rollback,
    describe_chat_page,
    show_rollback_button,
    wait_until_api_is_quiet,
)
from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_ALREADY_UNDONE = re.compile(r"already undone|已撤销或链接已失效")
# The server's own sentence for the 409; the user must only ever see the localized one.
_SERVER_SENTENCE = "No rollback snapshots"
_UNDONE_BUTTON_TEXT = re.compile(r"Changes reverted|已撤销修改")
_TOAST_SETTLE_SEC = 2.5

# A toast created earlier stays on screen while the page is hidden, so what the undo raised is told by the difference.
_TOASTS_JS = """(() => ({
  toasts: Array.from(document.querySelectorAll('[data-sonner-toast]')).map((node) => (node.textContent ?? '').trim()),
}))()"""

# What the user is left with once the 409 came back: the toasts on screen, the rollback requests the page made, and
# whether the open confirmation can be pressed again.
_OUTCOME_JS = """(() => {
  const toasts = Array.from(document.querySelectorAll('[data-sonner-toast]')).map((node) => (node.textContent ?? '').trim());
  const trace = window.__MYRM_ROLLBACK_TRACE__ ?? [];
  const confirm = document.querySelector('[data-testid="skill-manage-rollback-confirm"]');
  const button = document.querySelector('[data-testid="skill-manage-rollback-button"]');
  return {
    ready: trace.some((record) => record.status === 409) && toasts.some((text) => /already undone|已撤销或链接已失效/.test(text)),
    toasts,
    statuses: trace.map((record) => record.status ?? record.error ?? null),
    confirmEnabled: Boolean(confirm && !confirm.disabled),
    buttonText: button?.textContent?.trim() ?? null,
  };
})()"""

_CANCEL_DIALOG_JS = """(() => {
  const cancel = Array.from(document.querySelectorAll('[role="alertdialog"] button')).find((node) => !node.dataset.testid);
  if (!cancel) return { ok: false, err: 'missing-cancel-button' };
  cancel.click();
  return { ok: true };
})()"""

_DIALOG_CLOSED_JS = """(() => {
  const button = document.querySelector('[data-testid="skill-manage-rollback-button"]');
  return { ready: !document.querySelector('[role="alertdialog"]') && Boolean(button && !button.disabled) };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_undo_of_a_save_already_undone_elsewhere_says_so_once_and_leaves_the_skill_alone() -> None:
    """A second tab undid the save first: the real 409 reaches the user as one localized message, nothing changes."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    seed = _seed_mutation_batch(api_url)
    batch_id, skill_id = seed["batch_id"], seed["skill_id"]
    marker_v1, marker_v2 = seed["marker_v1"], seed["marker_v2"]

    undone_elsewhere = http_json("POST", f"{api_url}/api/v1/skill-optimization/mutations/{batch_id}/rollback")
    assert isinstance(undone_elsewhere, dict) and undone_elsewhere.get("status") == "rolled_back", undone_elsewhere
    restored = _fetch_skill_md(api_url, skill_id)
    assert marker_v1 in restored and marker_v2 not in restored, "the other tab's undo did not restore the skill"

    prepare_e2e_ui_session(api_url)
    chat_id = _seed_chat_with_batch(api_url, batch_id)
    target_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(target_url, timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=target_url)
        bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=120.0, page_url=target_url)
        assert bridge.get("ready") is True, bridge

        wait_until_api_is_quiet(client, page, api_url, stage="before-chat-load")
        attached = wait_for_state(client, page, _attach_probe_js(chat_id), timeout_sec=_ATTACH_TIMEOUT_SEC, page_url=target_url)
        assert attached.get("ready") is True, attached

        wait_until_api_is_quiet(client, page, api_url, stage="before-undo")
        show_rollback_button(client, page, target_url, describe=lambda: describe_chat_page(client, page))
        watched = client.evaluate(page, _WATCH_ROLLBACK_JS, timeout_sec=10.0)
        assert isinstance(watched, dict) and watched.get("ok") is True, watched
        before = client.evaluate(page, _TOASTS_JS, timeout_sec=10.0)
        assert isinstance(before, dict) and isinstance(before["toasts"], list), before
        confirm_rollback(client, page)

        try:
            wait_for_state(client, page, _OUTCOME_JS, timeout_sec=45.0, page_url=target_url)
        except AssertionError as failure:
            pytest.fail(f"{failure}\n{describe_chat_page(client, page)}")
        # A second, generic toast would arrive after the first (it is raised behind a dynamic import).
        time.sleep(_TOAST_SETTLE_SEC)
        outcome = client.evaluate(page, _OUTCOME_JS, timeout_sec=10.0)
        assert isinstance(outcome, dict), outcome
        print(f"E2E_CONSUMED_OUTCOME: {outcome}", flush=True)

        assert outcome["statuses"] == [409], f"exactly one undo request, refused as consumed: {outcome}"
        toasts = outcome["toasts"]
        assert isinstance(toasts, list), outcome
        raised = list((Counter(map(str, toasts)) - Counter(map(str, before["toasts"]))).elements())
        assert len(raised) == 1, f"one failed undo must raise one toast, not {raised}: {outcome}"
        assert _ALREADY_UNDONE.search(raised[0]), f"the toast does not say the batch was already undone: {raised}"
        assert _SERVER_SENTENCE not in raised[0], f"the server's English sentence reached the user: {raised}"
        assert outcome["confirmEnabled"] is True, f"the confirmation is stuck after the refusal: {outcome}"
        assert not _UNDONE_BUTTON_TEXT.search(str(outcome["buttonText"])), f"the panel claims the undo happened: {outcome}"

        content = _fetch_skill_md(api_url, skill_id)
        assert marker_v1 in content and marker_v2 not in content, "a refused undo changed the skill"

        cancelled = client.evaluate(page, _CANCEL_DIALOG_JS, timeout_sec=10.0)
        assert isinstance(cancelled, dict) and cancelled.get("ok") is True, cancelled
        closed = wait_for_state(client, page, _DIALOG_CLOSED_JS, timeout_sec=15.0, page_url=target_url)
        assert closed.get("ready") is True, closed
