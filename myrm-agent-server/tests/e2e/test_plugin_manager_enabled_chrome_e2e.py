"""Chrome E2E: Plugin Manager dialog shows MCP server enabled/disabled badges.

Real user flow on /settings/skills (Skills tab): open the "Manage Plugins"
dialog and verify each imported MCP server renders its persisted ``enabled``
state (green dot + "Enabled" vs amber dot + "Disabled" + hint tooltip).

The backend /api/v1/plugins/import/installed endpoint is exercised over the real
shared backend (no LLM, no zip upload): the mcpServers row is seeded directly
through the real ConfigService API so the dialog displays real persisted state.
"""

from __future__ import annotations

import time

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

_PLUGIN_NAME = "e2e-plugin"
_ENABLED_SERVER = "e2e-enabled-srv"
_DISABLED_SERVER = "e2e-disabled-srv"

_MANAGER_AVAILABLE_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button[title]')).find(
    (el) => /Manage Plugins|管理插件/.test(el.getAttribute('title') || ''),
  );
  return { ready: !!btn, text: (document.body?.innerText || '').slice(0, 300) };
})()"""

# The Manage Plugins button is an icon button with a title attribute. The
# "Installed" subtab must be active first (default subtab on non-sandbox
# deployments is "Discover"), then the button appears next to the skill rows.
_INSTALLED_TAB_READY_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((el) => {
    const text = (el.textContent || '').trim();
    return /^(Installed|已安装|已安裝)(\\d*)$/.test(text);
  });
  if (!btn) return { ready: false, err: 'installed-tab-not-found' };
  return { ready: true };
})()"""

# The Manage Plugins button is an icon button, so match by its title attribute.
_OPEN_MANAGER_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button[title]')).find(
    (el) => /Manage Plugins|管理插件/.test(el.getAttribute('title') || ''),
  );
  if (!btn) return { ok: false, err: 'manager-button-not-found' };
  btn.click();
  return { ok: true };
})()"""

# The Manage Plugins button renders only on the "Installed" subtab. Default on
# non-sandbox deployments is "Discover", so switch tabs first.
_CLICK_INSTALLED_TAB_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find((el) => {
    const text = (el.textContent || '').trim();
    return /^(Installed|已安装|已安裝)(\\d*)$/.test(text);
  });
  if (!btn) return { ok: false, err: 'installed-tab-not-found' };
  btn.click();
  return { ok: true };
})()"""

_DIALOG_READY_JS = """(() => {
  const dialog = Array.from(document.querySelectorAll('[role="dialog"]')).find((node) => {
    const text = node.textContent || '';
    return /Manage Plugins|管理插件/.test(text);
  });
  if (!dialog) return { ready: false, err: 'manager-dialog-not-found', text: (document.body?.innerText || '').slice(0, 1200) };
  const text = dialog.textContent || '';
  return {
    ready: /e2e-plugin/.test(text),
    hasEnabled: text.includes('e2e-enabled-srv') && /Active|已启用/.test(text),
    hasDisabled: text.includes('e2e-disabled-srv') && /Disabled|已禁用/.test(text),
    dialogText: text.slice(0, 1500),
  };
})()"""

_DIALOG_SERVER_BADGES_JS = """(() => {
  const dialog = Array.from(document.querySelectorAll('[role="dialog"]')).find((node) => {
    const text = node.textContent || '';
    return /Manage Plugins|管理插件/.test(text);
  });
  if (!dialog) return { ready: false, err: 'manager-dialog-not-found' };
  const text = dialog.textContent || '';
  const enabledDot = dialog.querySelector('.bg-emerald-500');
  const disabledDot = dialog.querySelector('.bg-amber-500');
  const hint = dialog.querySelector('.cursor-help');
  return {
    ready: true,
    hasEnabledDot: !!enabledDot,
    hasDisabledDot: !!disabledDot,
    hasHintTooltip: !!hint,
    hintTitle: hint ? (hint.getAttribute('title') || '') : '',
    text: text.slice(0, 1500),
  };
})()"""


def _seed_plugin_mcp_servers() -> None:
    """Persist an imported plugin's MCP servers through the real config API."""
    record = http_json("GET", f"{get_e2e_api_url()}/api/v1/config/mcpServers")
    assert isinstance(record, dict)
    version = str(record.get("version") or "0")
    payload = {
        "deviceId": "web",
        "expectedVersion": version,
        "value": {
            "mcpConfigs": [
                {
                    "name": _ENABLED_SERVER,
                    "type": "stdio",
                    "command": "echo",
                    "args": ["pass"],
                    "description": "E2E enabled probe",
                    "enabled": True,
                    "extra_params": {"plugin_name": _PLUGIN_NAME},
                },
                {
                    "name": _DISABLED_SERVER,
                    "type": "stdio",
                    "command": "echo",
                    "args": ["pass"],
                    "description": "E2E disabled probe",
                    "enabled": False,
                    "extra_params": {"plugin_name": _PLUGIN_NAME},
                },
            ]
        },
    }
    http_json("PUT", f"{get_e2e_api_url()}/api/v1/config/mcpServers", payload)

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        installed = http_json(
            "GET", f"{get_e2e_api_url()}/api/v1/plugins/import/installed"
        )
        assert isinstance(installed, list)
        plugin = next((p for p in installed if p.get("name") == _PLUGIN_NAME), None)
        if plugin and {s["name"] for s in plugin.get("server_meta", [])} == {
            _ENABLED_SERVER,
            _DISABLED_SERVER,
        }:
            return
        time.sleep(0.5)
    raise AssertionError("failed to seed plugin mcp servers via installed API")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_plugin_manager_shows_mcp_server_enabled_badges() -> None:
    """Real user flow: Manage Plugins dialog reflects persisted enabled state."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    _seed_plugin_mcp_servers()

    warm_ui_route("/settings/skills")
    with open_settings_subroute("/settings/skills", timeout_ms=120_000) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        tab_ready = wait_for_state(
            client, page, _INSTALLED_TAB_READY_JS, timeout_sec=90.0
        )
        assert tab_ready.get("ready") is True, tab_ready

        switched = client.evaluate(page, _CLICK_INSTALLED_TAB_JS, timeout_sec=20.0)
        assert isinstance(switched, dict) and switched.get("ok") is True, switched

        manager_ready = wait_for_state(
            client, page, _MANAGER_AVAILABLE_JS, timeout_sec=60.0
        )
        assert manager_ready.get("ready") is True, manager_ready

        opened = client.evaluate(page, _OPEN_MANAGER_JS, timeout_sec=20.0)
        assert isinstance(opened, dict) and opened.get("ok") is True, opened

        dialog = wait_for_state(client, page, _DIALOG_READY_JS, timeout_sec=60.0)
        assert dialog.get("ready") is True, dialog
        assert dialog.get("hasEnabled") is True, dialog
        assert dialog.get("hasDisabled") is True, dialog

        badges = client.evaluate(page, _DIALOG_SERVER_BADGES_JS, timeout_sec=20.0)
        assert isinstance(badges, dict) and badges.get("ready") is True, badges
        assert badges.get("hasEnabledDot") is True, badges
        assert badges.get("hasDisabledDot") is True, badges
        assert badges.get("hasHintTooltip") is True, badges
        assert "MCP Settings" in badges.get(
            "hintTitle", ""
        ) or "MCP 设置" in badges.get("hintTitle", ""), badges
        print(f"[plugin-manager-e2e] badge hint tooltip: {badges.get('hintTitle')}")
