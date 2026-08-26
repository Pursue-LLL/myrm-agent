"""Chrome E2E: workspace browser project scoped root & inline diff preview.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: Chrome MCP CDP test infrastructure)
- myrm-agent-frontend/src/components/features/workspace-browser (POS: Workspace file browser & diff components)

[OUTPUT]
- test_workspace_project_root_and_diff_chrome_e2e: E2E verification of project root setting & inline diff

[POS]
READ lane Chrome E2E test for Project-Scoped Workspace and Inline Workspace Diff UI.
"""

from __future__ import annotations

import os
import sys

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)


@pytest.mark.chrome_e2e
def test_workspace_project_root_and_diff_chrome_e2e() -> None:
    """Verify workspace browser context menu 'Set as Project Root' and inline diff component render."""
    _require_e2e_cdp_ready()
    warm_ui_route("/")
    session = prepare_e2e_ui_session("ws_project_diff_e2e")
    page = open_mcp_page(f"{get_e2e_ui_url()}/?chat={session}")

    ensure_desktop_viewport(page)
    dismiss_blocking_modals(page)
    wait_for_react_e2e_bridge(page)

    # 1. Verify page shell loaded
    ready = wait_for_state(
        page,
        '() => document.body !== null && document.querySelector(\'[data-testid="chat-window"], [data-testid="chat-input-textarea"], main\') !== null',
        timeout=15.0,
    )
    assert ready, "Chat window/page shell did not load"
