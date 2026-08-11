"""Real Chrome MCP E2E for Browser Live Co-View (BLCV) bridge contract."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
)

_BRIDGE_READY_JS = """(() => ({
  ready:
    typeof window.__MYRM_E2E_CHAT__?.getBrowserInspectorSnapshot === 'function' &&
    typeof window.__MYRM_E2E_CHAT__?.getBrowserToolProgress === 'function',
  snapshot: window.__MYRM_E2E_CHAT__?.getBrowserInspectorSnapshot?.() ?? null,
}))()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_browser_inspector_blcv_bridge_exposed_in_real_ui() -> None:
    """Chat shell exposes BLCV inspector snapshot bridge for SSE-driven live view."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(ui_url)

    with open_mcp_page(f"{ui_url.rstrip('/')}/") as (client, page):
        dismiss_blocking_modals(client, page)
        state = wait_for_state(
            client,
            page,
            _BRIDGE_READY_JS,
            timeout_sec=60.0,
            page_url=f"{ui_url.rstrip('/')}/",
        )
        assert state.get("ready") is True, state
        snapshot = state.get("snapshot")
        assert isinstance(snapshot, dict), snapshot
        assert snapshot.get("isOpen") is False
        assert snapshot.get("isBrowserActive") is False
        assert snapshot.get("hasScreenshot") is False
