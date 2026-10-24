"""Chrome E2E: the Agent editor binds a built-in specialist through the real Subagents UI.

Covers the user-facing chain for the subagent catalog:
  T1 - Settings > Agents opens a custom agent editor.
  T2 - Capabilities exposes the Subagents card and its built-in specialist catalog.
  T3 - Selecting Codebase Explorer updates the card, Save persists subagent_ids via the real API.
  T4 - Cleanup removes the seeded agent.
"""

from __future__ import annotations

import json
import time
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

_OPEN_SUBAGENTS_JS = """(() => {
  const tab = document.querySelector('[data-testid="agent-tab-capabilities"]');
  if (!tab) return { ready: false, reason: 'no-capabilities-tab' };
  tab.click();
  return new Promise(resolve => setTimeout(() => {
    const add = Array.from(document.querySelectorAll('button')).find((button) =>
      /Add Subagent|添加子智能体|新增子智慧體|サブエージェントを追加|하위 에이전트 추가|Subagent hinzufügen/i.test(button.textContent || ''),
    );
    if (!add) {
      return resolve({
        ready: false,
        reason: 'no-add-subagent-button',
        body: (document.body?.innerText || '').slice(0, 800),
      });
    }
    add.click();
    resolve({ ready: true });
  }, 400));
})()"""

_SELECT_EXPLORE_JS = """(() => {
  const target = Array.from(document.querySelectorAll('button')).find((button) =>
    /Codebase Explorer|代码库探索专家|程式碼庫探索專家|コードベース探索|코드베이스 탐색|Codebase-Explorer/i.test(button.textContent || '') &&
    button.offsetParent !== null,
  );
  if (!target) {
    return {
      ready: false,
      body: (document.body?.innerText || '').slice(0, 500),
    };
  }
  target.click();
  return new Promise(resolve => setTimeout(() => {
    resolve({
      ready: true,
      body: (document.body?.innerText || '').slice(0, 500),
    });
  }, 300));
})()"""

_CLICK_SAVE_JS = """(() => {
  const section = document.querySelector('[data-section="agents"]') || document.body;
  const save = Array.from(section.querySelectorAll('button')).find((button) =>
    /^(Save|保存|儲存)$/i.test((button.textContent || '').trim()) &&
    button.offsetParent !== null &&
    !button.disabled,
  );
  if (!save) return { ready: false, reason: 'no-enabled-save-button' };
  save.click();
  return { ready: true };
})()"""

_SAVE_COMPLETE_JS = """(() => {
  const section = document.querySelector('[data-section="agents"]') || document.body;
  const save = Array.from(section.querySelectorAll('button')).find((button) =>
    /^(Save|保存|儲存)$/i.test((button.textContent || '').trim()) && button.offsetParent !== null,
  );
  if (!save) return { ready: false, reason: 'no-visible-save-button' };
  return { ready: save.disabled && !save.querySelector('.animate-spin'), disabled: save.disabled };
})()"""


def _create_agent(api_url: str, *, name: str) -> str:
    response = http_json("POST", f"{api_url}/api/v1/user-agents", {"name": name})
    data = response["data"]
    agent_id = data.get("id") or data.get("agent_id")
    assert isinstance(agent_id, str) and agent_id, json.dumps(data, ensure_ascii=False)
    return agent_id


def _fetch_subagent_ids(api_url: str, agent_id: str) -> list[str]:
    response = http_json("GET", f"{api_url}/api/v1/user-agents/{agent_id}")
    return list((response.get("data") or {}).get("subagent_ids") or [])


def _wait_subagent_ids(api_url: str, agent_id: str, expected: list[str], *, timeout_sec: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last: list[str] = []
    while time.monotonic() < deadline:
        last = _fetch_subagent_ids(api_url, agent_id)
        if last == expected:
            return
        time.sleep(1.0)
    raise AssertionError(f"subagent_ids did not persist: expected={expected} last={last}")


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_agent_subagent_picker_persists_explore() -> None:
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    name = f"subagent-picker-{uuid.uuid4().hex[:8]}"
    agent_id = _create_agent(api_url, name=name)
    try:
        assert _fetch_subagent_ids(api_url, agent_id) == []

        warm_ui_route("/settings")
        edit_url = f"{get_e2e_ui_url().rstrip('/')}{_EDIT_URL}{agent_id}"
        with open_settings_subroute(
            edit_url.replace(get_e2e_ui_url().rstrip("/"), ""),
            timeout_ms=120_000,
        ) as (client, page):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page)

            opened = wait_for_state(
                client,
                page,
                _OPEN_SUBAGENTS_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(60.0),
            )
            assert opened.get("ready") is True, json.dumps(opened, indent=2, ensure_ascii=False)

            selected = wait_for_state(
                client,
                page,
                _SELECT_EXPLORE_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(30.0),
            )
            assert selected.get("ready") is True, json.dumps(selected, indent=2, ensure_ascii=False)

            clicked = wait_for_state(
                client,
                page,
                _CLICK_SAVE_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(20.0),
            )
            assert clicked.get("ready") is True, json.dumps(clicked, indent=2, ensure_ascii=False)

            saved = wait_for_state(
                client,
                page,
                _SAVE_COMPLETE_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(30.0),
            )
            assert saved.get("ready") is True, json.dumps(saved, indent=2, ensure_ascii=False)

        _wait_subagent_ids(api_url, agent_id, ["explore"])
    finally:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
