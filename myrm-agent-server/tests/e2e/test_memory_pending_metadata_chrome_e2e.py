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
  const [pendingRes, conflictsRes, batchApproveRes, batchRejectRes] = await Promise.all([
    fetch('/api/v1/memory/pending', { cache: 'no-store' }),
    fetch('/api/v1/memory/conflicts', { cache: 'no-store' }),
    // Empty-list batch calls are a no-mutation contract probe: they must resolve
    // to the batch handler (not be swallowed by /pending/{memory_id}/approve,
    // which would echo memory_id="batch").
    fetch('/api/v1/memory/pending/batch/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ memory_ids: [] }),
    }),
    fetch('/api/v1/memory/pending/batch/reject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ memory_ids: [] }),
    }),
  ]);
  if (!pendingRes.ok || !conflictsRes.ok || !batchApproveRes.ok || !batchRejectRes.ok) {
    return {
      ok: false,
      pendingStatus: pendingRes.status,
      conflictsStatus: conflictsRes.status,
      batchApproveStatus: batchApproveRes.status,
      batchRejectStatus: batchRejectRes.status,
    };
  }
  const pendingData = await pendingRes.json();
  const conflictsData = await conflictsRes.json();
  const batchApprove = await batchApproveRes.json();
  const batchReject = await batchRejectRes.json();
  const hasValidPending = Array.isArray(pendingData) || (pendingData && Array.isArray(pendingData.items));
  const hasValidConflicts = Array.isArray(conflictsData) || (conflictsData && Array.isArray(conflictsData.items));
  // A real batch handler returns BatchMemoryResponse; the shadowed route returned
  // a StandardSuccessResponse envelope ({success, code, data}).
  const isBatchShape = (body) =>
    body && typeof body.success_count === 'number' && Array.isArray(body.failed_ids) && body.code === undefined;
  return {
    ok:
      hasValidPending &&
      hasValidConflicts &&
      isBatchShape(batchApprove) &&
      isBatchShape(batchReject),
    hasValidPending,
    hasValidConflicts,
    batchApprove,
    batchReject,
    text: document.body?.textContent?.slice(0, 500) || '',
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_pending_metadata_chrome_e2e() -> None:
    """Browser same-origin fetch verifies the pending/conflicts/batch memory contracts in WebUI.

    Declared PRIVATE because it asserts workspace backend behaviour (batch route
    dispatch + pending candidate metadata), which requires a workspace-epoch backend.
    """
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=90_000) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        browser_body = client.evaluate(page, _PENDING_METADATA_CHECK_JS)
        assert browser_body.get("ok") is True, browser_body
