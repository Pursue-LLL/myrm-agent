"""Chrome READ E2E: SecurityPreset session lifecycle (no LLM).

Covers the three-tier session security preset (hitl / accept_edits / explore)
end-to-end through the WebUI:

1. Initialization  — opening a chat bound to an agent whose
   `default_security_preset=accept_edits` must hydrate the store's
   session `securityPreset` to `accept_edits`.
2. UI interaction  — clicking the SecurityPresetSelector dropdown and picking
   `explore` must update the store session `securityPreset` to `explore`.
3. Fail-closed      — opening a chat bound to an agent *without* a
   `default_security_preset` must fall back to `hitl`.

Store-level assertions use `window.__myrmChatStore` (the same bridge used by
other READ chrome E2E) so the assertions pin the session preset SSOT rather
than transient DOM text.
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)


def _seed_fixture(api_url: str) -> dict[str, str]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-security-preset-fixture",
    )
    assert isinstance(seeded, dict)
    preset_chat_id = str(seeded.get("preset_chat_id") or "")
    plain_chat_id = str(seeded.get("plain_chat_id") or "")
    assert preset_chat_id.startswith("e2esecpreset")
    assert plain_chat_id.startswith("e2esecpreset")
    assert str(seeded.get("preset_ui_path") or "").startswith("/")
    assert str(seeded.get("plain_ui_path") or "").startswith("/")
    return {key: str(seeded[key]) for key in seeded}


def _store_preset_probe(expected: str, agent_id: str | None = None) -> str:
    expected_json = json.dumps(expected)
    agent_json = json.dumps(agent_id) if agent_id else "null"
    return f"""(() => {{
  const store = window.__myrmChatStore?.getState?.();
  if (!store) return {{ ready: false, err: 'no-store' }};
  if ({agent_json} && store.agentConfig?.agentId !== {agent_json}) {{
    return {{ ready: false, err: 'agent-not-bound', agentId: store.agentConfig?.agentId ?? null }};
  }}
  const preset = store.securityPreset;
  return {{ ready: preset === {expected_json}, preset, err: null }};
}})()"""


_TRIGGER_READY_JS = """(() => {
  const trigger = document.querySelector('[data-testid="security-preset-trigger"]');
  return { ready: !!trigger, hasTrigger: !!trigger };
})()"""

_CLICK_OPTION_JS = """((preset) => {
  const option = document.querySelector(`[data-testid="security-preset-option-${preset}"]`);
  if (!option) return { ok: false, err: 'no-option', preset };
  option.click();
  return { ok: true, preset };
})"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_security_preset_initialization_and_ui_switch_and_fail_closed() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_fixture(api_url)
    preset_path = seeded["preset_ui_path"]
    plain_path = seeded["plain_ui_path"]
    preset_agent_id = seeded["preset_agent_id"]
    plain_agent_id = seeded["plain_agent_id"]

    # --- Scenario 1: initialization to agent default preset ---
    warm_ui_route(preset_path)
    with open_mcp_page(f"{ui_url}{preset_path}", timeout_ms=120_000) as (client, page):
        init_state = wait_for_state(
            client,
            page,
            _store_preset_probe("accept_edits", preset_agent_id),
            timeout_sec=90.0,
        )
        assert init_state.get("ready") is True, json.dumps(
            init_state, ensure_ascii=False
        )

        trigger_state = wait_for_state(
            client,
            page,
            _TRIGGER_READY_JS,
            timeout_sec=30.0,
        )
        assert trigger_state.get("ready") is True, json.dumps(
            trigger_state, ensure_ascii=False
        )

        # --- Scenario 2: UI switch to explore via dropdown ---
        clicked = client.evaluate(
            page,
            "((preset) => { const t = document.querySelector('[data-testid=\"security-preset-trigger\"]'); if (!t) return { ok: false, err: 'no-trigger' }; t.click(); return { ok: true }; })('explore')",
            timeout_sec=15.0,
        )
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        option_state = wait_for_state(
            client,
            page,
            """(() => {
  const option = document.querySelector('[data-testid="security-preset-option-explore"]');
  return { ready: !!option };
})()""",
            timeout_sec=15.0,
        )
        assert option_state.get("ready") is True, json.dumps(
            option_state, ensure_ascii=False
        )

        clicked_option = client.evaluate(
            page,
            _CLICK_OPTION_JS,
            "explore",
            timeout_sec=15.0,
        )
        assert isinstance(clicked_option, dict) and clicked_option.get("ok") is True, (
            clicked_option
        )

        switch_state = wait_for_state(
            client,
            page,
            _store_preset_probe("explore"),
            timeout_sec=30.0,
        )
        assert switch_state.get("ready") is True, json.dumps(
            switch_state, ensure_ascii=False
        )

    # --- Scenario 3: fail-closed fallback to hitl on an agent without default ---
    warm_ui_route(plain_path)
    with open_mcp_page(f"{ui_url}{plain_path}", timeout_ms=120_000) as (client, page):
        fallback_state = wait_for_state(
            client,
            page,
            _store_preset_probe("hitl", plain_agent_id),
            timeout_sec=90.0,
        )
        assert fallback_state.get("ready") is True, json.dumps(
            fallback_state, ensure_ascii=False
        )
