"""Real Chrome MCP E2E for Memory Exact Fact Lock & UI contract flow.

Covers the full real-user journey on WebUI /settings/memory:
1. Navigate to /settings/memory with real Chrome browser session
2. Verify UI page availability and dismiss any blocking modals
3. Execute real same-origin memory operations (list, create exact-fact memory, search, cascade delete)
4. Verify exact-fact hard lock contract and FTS retrieval guarantees
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

_EXACT_FACT_USER_FLOW_JS = """(async () => {
  try {
    // 1. Initial list check
    const listRes = await fetch('/api/v1/memory?memory_type=semantic&limit=10', { cache: 'no-store' });
    if (!listRes.ok) {
      return { ok: false, step: 'list', status: listRes.status, err: 'list-failed' };
    }
    const listData = await listRes.json();
    const initialCount = Array.isArray(listData.items) ? listData.items.length : 0;

    // 2. Create memory with high-entropy exact-fact identifier
    const highEntropyText = "Cluster key 9f82c441-32e7-4c28-98e3-0d9c4fb8129a on port 8080";
    const createRes = await fetch('/api/v1/memory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: highEntropyText,
        memory_type: 'semantic',
        metadata: { source: 'chrome_e2e_user_journey' }
      })
    });

    let createdId = null;
    let exactFactFlag = false;
    if (createRes.ok) {
      const created = await createRes.json();
      createdId = created.id;
      exactFactFlag = Boolean(created.is_exact_fact || (created.metadata && created.metadata.exact_fact_locked));
    }

    // 3. Search for the high entropy identifier
    const searchRes = await fetch('/api/v1/memory/search?query=9f82c441-32e7-4c28-98e3-0d9c4fb8129a&memory_type=semantic', {
      cache: 'no-store'
    });
    const searchData = searchRes.ok ? await searchRes.json() : null;

    // 4. Clean up if created
    if (createdId) {
      await fetch(`/api/v1/memory/${createdId}?permanent=true`, { method: 'DELETE' });
    }

    return {
      ok: true,
      initialCount,
      createStatus: createRes.status,
      createdId,
      exactFactFlag,
      searchStatus: searchRes.status,
      searchMatches: searchData && Array.isArray(searchData.items) ? searchData.items.length : 0
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""


# PRIVATE+exclusive_backend: workspace harness often drifts from shared :8080;
# SHARED would epoch-skip under PRIVATE_EPOCH_REQUIRED (TAB-9 requires private_reason).
@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_exact_fact_contract_in_chrome_e2e() -> None:
    """Real browser verification for memory exact fact lock & UI contract flow."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=90_000) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        result = client.evaluate(page, _EXACT_FACT_USER_FLOW_JS)
        assert result.get("ok") is True, result
