"""Real Chrome MCP E2E: push approval deeplink navigates on an already-open chat tab."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
)

_APPROVAL_DIALOG_STATE = """(() => ({
  ready: !!document.querySelector('[role="dialog"]'),
  pathname: location.pathname,
  search: location.search,
}))()"""

_NO_APPROVAL_DIALOG_STATE = """(() => ({
  ready: !document.querySelector('[role="dialog"]'),
  hasChatInput: !!document.querySelector('[data-chat-input]'),
}))()"""

_DISMISS_APPROVAL_DIALOG_JS = """(() => {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return { dismissed: false };
  const closeBtn = dialog.querySelector(
    '[data-testid="dialog-close"], button[aria-label*="Close" i], button'
  );
  closeBtn?.click();
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  return { dismissed: true };
})()"""


def _ensure_clean_chat_surface(client, page) -> None:
    for _ in range(8):
        state = wait_for_state(
            client,
            page,
            _NO_APPROVAL_DIALOG_STATE,
            timeout_sec=15.0,
        )
        if state.get("ready") is True:
            return
        client.evaluate(page, _DISMISS_APPROVAL_DIALOG_JS, timeout_sec=5.0)
    raise AssertionError("Could not clear approval dialog before deeplink baseline")


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_push_approval_deeplink_navigates_on_open_chat_tab() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    seeded = http_json("POST", f"{api_url}/api/v1/approvals/test/seed-mock")
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    approval_id = str(seeded.get("approval_id") or "")
    push_url = str(seeded.get("push_url") or "")
    assert len(chat_id) >= 8
    assert approval_id
    assert push_url.startswith(f"/{chat_id}?approval={approval_id}")

    chat_url = f"{ui_url}/{chat_id}"
    deeplink_url = f"{ui_url}{push_url}"

    with open_mcp_page(chat_url) as (client, page):
        _ensure_clean_chat_surface(client, page)
        baseline = wait_for_state(client, page, _NO_APPROVAL_DIALOG_STATE, timeout_sec=30.0)
        assert baseline.get("ready") is True
        assert baseline.get("hasChatInput") is True

        client.navigate(page, deeplink_url, timeout_ms=60_000)

        opened = wait_for_state(client, page, _APPROVAL_DIALOG_STATE, timeout_sec=90.0)
        assert opened.get("ready") is True
        assert str(opened.get("search") or "").startswith(f"?approval={approval_id}")

    resolved = http_json(
        "POST",
        f"{api_url}/api/v1/approvals/{approval_id}/resolve",
        {"decision": "deny"},
    )
    assert isinstance(resolved, dict)
    assert resolved.get("status") == "REJECTED"
