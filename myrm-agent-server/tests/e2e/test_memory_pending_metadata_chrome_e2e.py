"""Chrome READ E2E: Memory pending candidate structured metadata contract and settings view."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    warm_ui_route,
)

_PENDING_METADATA_CHECK_JS = """(async () => {
  const [pendingRes, conflictsRes] = await Promise.all([
    fetch('/api/v1/memory/pending', { cache: 'no-store' }),
    fetch('/api/v1/memory/conflicts', { cache: 'no-store' }),
  ]);
  if (!pendingRes.ok || !conflictsRes.ok) {
    return {
      ok: false,
      pendingStatus: pendingRes.status,
      conflictsStatus: conflictsRes.status,
    };
  }
  const pendingData = await pendingRes.json();
  const conflictsData = await conflictsRes.json();
  const hasValidPending = Array.isArray(pendingData) || (pendingData && Array.isArray(pendingData.items));
  const hasValidConflicts = Array.isArray(conflictsData) || (conflictsData && Array.isArray(conflictsData.items));
  return {
    ok: hasValidPending && hasValidConflicts,
    hasValidPending,
    hasValidConflicts,
    text: document.body?.textContent?.slice(0, 500) || '',
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_pending_metadata_chrome_e2e() -> None:
    """Browser same-origin fetch verifies pending candidate structured metadata contract in WebUI."""
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=90_000) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        browser_body = client.evaluate(page, _PENDING_METADATA_CHECK_JS)
        assert browser_body.get("ok") is True, browser_body
