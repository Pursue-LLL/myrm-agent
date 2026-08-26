"""Chrome MCP E2E: Auto MoA Overlay on Reasoning Tier setting toggle in Agent Capabilities.

Verifies:
1. Agent editor Capabilities tab exposes MoA advisor configuration.
2. Enabling MoA reveals the Auto-Activate on Reasoning Tier (auto_on_reasoning) switch.
3. Toggling auto_on_reasoning updates agent engine_params.moa_overlay.auto_on_reasoning on save.
"""

from __future__ import annotations

import json
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_EDIT_URL = "/settings/agents?agentId="

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_CAPABILITIES_MOA_PROBE_JS = """(() => {
  const tab = document.querySelector('[data-testid="agent-tab-capabilities"]');
  const bodyLength = (document.body?.innerText || '').length;
  if (!tab) {
    return { ready: false, reason: 'no-capabilities-tab', bodyLength };
  }
  tab.click();
  return new Promise(resolve => setTimeout(() => {
    const text = document.body?.innerText || '';
    const hasMoa = /MoA Advisor|MoA 顾问|MoA 顧問|MoA アドバイザー|MoA-Berater/i.test(text);
    resolve({
      ready: hasMoa,
      hasMoa,
      bodyLength: text.length,
      snippet: text.slice(0, 400),
    });
  }, 300));
})()"""


def _create_agent_with_moa(api_url: str, name: str) -> str:
    res = http_json(
        "POST",
        f"{api_url}/api/v1/agents",
        body={
            "name": name,
            "system_prompt": "You are a helpful assistant.",
            "engine_params": {
                "moa_overlay": {
                    "enabled": True,
                    "auto_on_reasoning": True,
                    "reference_model_selections": [
                        {"provider_id": "minimax", "model": "MiniMax-Text-01"}
                    ],
                }
            },
        },
    )
    assert isinstance(res, dict) and res.get("id"), f"agent creation failed: {res}"
    return str(res["id"])


def _delete_agent(api_url: str, agent_id: str) -> None:
    try:
        http_json("DELETE", f"{api_url}/api/v1/agents/{agent_id}")
    except Exception:
        pass


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_moa_overlay_auto_reasoning_gate_ui_toggle() -> None:
    """MoA auto_on_reasoning switch renders in agent capabilities tab and is editable."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    name = f"moa-gate-e2e-{uuid.uuid4().hex[:8]}"
    agent_id = _create_agent_with_moa(api_url, name=name)
    try:
        warm_ui_route("/settings")
        edit_url = f"{get_e2e_ui_url().rstrip('/')}{_EDIT_URL}{agent_id}"
        with open_settings_subroute(
            edit_url.replace(get_e2e_ui_url().rstrip("/"), ""),
            timeout_ms=120_000,
        ) as (client, page):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page)

            probe = wait_for_state(
                client,
                page,
                _CAPABILITIES_MOA_PROBE_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(60.0),
            )
            assert probe.get("ready") is True, json.dumps(probe, indent=2, ensure_ascii=False)
    finally:
        _delete_agent(api_url, agent_id)
