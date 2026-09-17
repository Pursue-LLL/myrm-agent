"""Chrome E2E: workspace review workbench (/work) shell render smoke.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: Chrome MCP CDP test infrastructure)
- myrm-agent-frontend/src/components/features/workspace (POS: 工作区文件树、浏览器与沙箱文件操作 UI)

[OUTPUT]
- test_workspace_review_panel_shell_chrome_e2e: E2E verification of /work shell render

[POS]
READ lane Chrome E2E test for the workspace review workbench shell
(WorkspaceLayout + ReviewPanel bundle load, empty-state render).
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_workspace_review_panel_shell_chrome_e2e() -> None:
    """Verify /work renders the review workbench shell without chunk errors."""
    _require_e2e_cdp_ready()
    warm_ui_route("/work")
    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)
    with open_mcp_page(f"{get_e2e_ui_url()}/work") as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        wait_for_react_e2e_bridge(client, page)

        ready = wait_for_state(
            client,
            page,
            '(() => ({ ready: Boolean(document.querySelector("h1") && document.querySelector("h1").textContent.trim().length > 0) }))()',
            timeout_sec=60.0,
        )
        assert ready.get("ready") is True, "Workspace workbench header did not render"

        no_fatal = wait_for_state(
            client,
            page,
            '(() => ({ ready: !document.querySelector("[data-nextjs-dialog-overlay], [data-nextjs-error]") }))()',
            timeout_sec=30.0,
        )
        assert no_fatal.get("ready") is True, "Next.js fatal overlay present on /work"
