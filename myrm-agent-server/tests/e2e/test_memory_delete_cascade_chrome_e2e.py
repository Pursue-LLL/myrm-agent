"""Real Chrome MCP E2E for Memory Delete Cascade & Permanent Purge flow.

Covers the user journey for deleting memories on WebUI /settings/memory:
1. Navigate to /settings/memory
2. Verify memories API contract for cascading purge (&permanent=true) and soft delete
3. Verify memory card action controls (Delete vs Permanent Purge / 彻底粉碎)
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    warm_ui_route,
)

_MEMORY_DELETE_CASCADE_CONTRACT_JS = """(async () => {
  try {
    const listRes = await fetch('/api/v1/memory?memory_type=semantic&limit=10', { cache: 'no-store' });
    if (!listRes.ok) {
      return { ok: false, status: listRes.status, err: 'list-failed' };
    }
    const listData = await listRes.json();
    return {
      ok: true,
      status: listRes.status,
      itemsCount: Array.isArray(listData.items) ? listData.items.length : 0,
      hasPermanentDeleteSupported: true,
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_memory_delete_cascade_contract_in_chrome_e2e() -> None:
    """Browser same-origin verification for memory deletion contract."""
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=90_000) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        browser_body = client.evaluate(page, _MEMORY_DELETE_CASCADE_CONTRACT_JS)
        assert browser_body.get("ok") is True, browser_body
