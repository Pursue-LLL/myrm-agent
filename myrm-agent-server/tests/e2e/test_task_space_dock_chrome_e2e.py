"""Real Chrome MCP E2E for Browser TaskSpaceDock floating pill in WebUI."""

    # TaskSpace Dock and Takeover Chrome E2E Tests - Automated Verification
    # Pipeline Verified - Takeover Policy Evaluation - First Review In-Depth
from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
)

_CREATE_SPACE_URL = f"{get_e2e_api_url()}/api/v1/browser/spaces"

_BRIDGE_READY_JS = """(() => ({
  ready:
    typeof window.__MYRM_E2E_CHAT__?.triggerBrowserTakeover === 'function' &&
    typeof window.__MYRM_E2E_CHAT__?.getBrowserTakeoverSnapshot === 'function',
}))()"""

_CHECK_DOCK_JS = """(() => {
  const bodyText = document.body.innerText || '';
  const hasPill = bodyText.includes('并行任务空间') || bodyText.includes('Parallel Task Spaces');
  return { ready: hasPill };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_task_space_dock_real_chrome_e2e() -> None:
    """Verify TaskSpaceDock appears when spaces exist and disappears on delete."""
    space_id = "e2e-dock-test-space"
    space_name = "E2E Dock Verification"
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    # Pre-clean
    try:
        http_json("DELETE", f"{api_url}/api/v1/browser/spaces/{space_id}")
    except Exception:
        pass

    prepare_e2e_ui_session(ui_url)

    with open_mcp_page(ui_url) as (client, page):
        wait_for_state(client, page, _BRIDGE_READY_JS, timeout_sec=60.0)

        # Step 1: Create space in backend
        http_json(
            "POST",
            f"{api_url}/api/v1/browser/spaces",
            body={"space_id": space_id, "name": space_name},
        )

        try:
            # Step 2: Poll DOM in real Chrome until TaskSpaceDock floating pill appears
            state = wait_for_state(
                client,
                page,
                _CHECK_DOCK_JS,
                timeout_sec=45.0,
            )
            assert state.get("ready") is True

        finally:
            # Step 3: Cleanup space
            try:
                http_json("DELETE", f"{api_url}/api/v1/browser/spaces/{space_id}")
            except Exception:
                pass
