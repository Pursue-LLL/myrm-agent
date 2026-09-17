"""Real Chrome MCP E2E for Three-Domain Memory Mesh panel.

Covers the real-user flow on the settings memory page:
1. Open /settings/memory and confirm Three-Domain Memory Mesh renders.
2. Confirm the Multi-Domain Sync badge is displayed.
3. Confirm the user-facing description is rendered without technical jargon.
4. Confirm all three domain cards (User, Assistant, Task) are properly displayed.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)

_DOMAIN_MESH_PANEL_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const hasTitle = text.includes('Three-Domain Memory Mesh');
  const hasBadge = text.includes('Multi-Domain Sync');
  const hasSub = text.includes('Intelligently organizes preferences, persona, and task experiences');
  const hasUser = text.includes('User Domain');
  const hasAssistant = text.includes('Assistant Domain');
  const hasTask = text.includes('Task Domain');

  return {
    ready: hasTitle && hasBadge && hasSub && hasUser && hasAssistant && hasTask,
    hasTitle,
    hasBadge,
    hasSub,
    hasUser,
    hasAssistant,
    hasTask,
    sample: text.slice(0, 1000),
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_three_domain_memory_mesh_chrome_e2e() -> None:
    """Real user flow: verify Three-Domain Memory Mesh panel copy, badge, and domain cards."""
    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (client, page):
        state = wait_for_state(client, page, _DOMAIN_MESH_PANEL_READY_JS, timeout_sec=90.0)
        assert state.get("ready") is True, state
        assert state.get("hasTitle") is True, state
        assert state.get("hasBadge") is True, state
        assert state.get("hasSub") is True, state
        assert state.get("hasUser") is True, state
        assert state.get("hasAssistant") is True, state
        assert state.get("hasTask") is True, state
