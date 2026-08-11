"""Chrome E2E: org-managed MCP servers render in the WebUI MCP settings page.

[INPUT]
- Control Plane pushes org-level MCP servers via POST /api/admin/org-mcp-sync

[OUTPUT]
- /settings/mcp shows an "Organization Managed" section listing synced servers
  as read-only cards (server name + Org badge), and hides the section once the
  org config is cleared.
"""

from __future__ import annotations

import json
import sys

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_ORG_PROBE_NAME = "org-e2e-probe"
_ORG_MCP_SYNC_PATH = "/api/admin/org-mcp-sync"
_ORG_MCP_READ_PATH = "/api/v1/config/orgMcpServers"

_ORG_MCP_CARD_JS = """(() => {
  const bodyText = document.body?.innerText || '';
  const hasTitle = /Organization Managed|组织统一管理/.test(bodyText);
  const nameEl = Array.from(document.querySelectorAll('p')).find(
    (p) => (p.textContent || '').trim() === 'org-e2e-probe'
  );
  let badgeText = null;
  let node = nameEl ? nameEl.closest('div') : null;
  while (node) {
    const span = Array.from(node.querySelectorAll('span')).find(
      (s) => /^(Org|组织)$/.test((s.textContent || '').trim())
    );
    if (span) { badgeText = span.textContent.trim(); break; }
    node = node.parentElement;
  }
  const ready = hasTitle && nameEl !== null && badgeText !== null;
  return { ready, hasTitle, hasName: nameEl !== null, badgeText, sample: bodyText.slice(0, 400) };
})()"""

_ORG_MCP_GONE_JS = """(() => {
  const bodyText = document.body?.innerText || '';
  const hasName = bodyText.includes('org-e2e-probe');
  return { ready: !hasName, sample: bodyText.slice(0, 400) };
})()"""


def _org_mcp_server_names(api_url: str) -> list[str]:
    record = http_json("GET", f"{api_url}{_ORG_MCP_READ_PATH}")
    assert isinstance(record, dict), record
    value = record.get("value") or {}
    servers = value.get("servers") or []
    assert isinstance(servers, list), servers
    return [str(s.get("name", "")) for s in servers if isinstance(s, dict)]


def _sync_org_mcp(api_url: str, servers: list[dict]) -> dict:
    result = http_json(
        "POST",
        f"{api_url}{_ORG_MCP_SYNC_PATH}",
        {"mcp_servers": servers},
    )
    assert isinstance(result, dict), result
    assert result.get("status") == "synced", result
    return result


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_org_mcp_frontend_display_chrome_e2e() -> None:
    """Org-managed MCP servers synced by CP render as read-only cards and disappear on clear."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    # Fresh start: no org-managed MCP servers.
    _sync_org_mcp(api_url, [])
    assert _org_mcp_server_names(api_url) == []

    # CP pushes an org-managed stdio MCP server.
    probe = {
        "name": _ORG_PROBE_NAME,
        "command": sys.executable,
        "args": ["-c", "pass"],
        "description": "E2E org-managed MCP probe",
    }
    synced = _sync_org_mcp(api_url, [probe])
    assert synced.get("count") == 1, synced
    assert _org_mcp_server_names(api_url) == [_ORG_PROBE_NAME]

    # The MCP settings page shows the org-managed server as a read-only card.
    warm_ui_route("/settings/mcp")
    with open_settings_subroute("/settings/mcp", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        ready = wait_for_state(client, page, _ORG_MCP_CARD_JS, timeout_sec=90.0)
        assert ready.get("ready") is True, json.dumps(ready, ensure_ascii=False)

    # Cleanup: clear org MCP config so the runtime stays pristine.
    _sync_org_mcp(api_url, [])
    assert _org_mcp_server_names(api_url) == []

    # Reload the page and confirm the org section disappears.
    with open_settings_subroute("/settings/mcp", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        gone = wait_for_state(client, page, _ORG_MCP_GONE_JS, timeout_sec=90.0)
        assert gone.get("ready") is True, json.dumps(gone, ensure_ascii=False)
