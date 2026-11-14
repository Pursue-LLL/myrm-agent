"""Chrome E2E: an agent deep link opens that agent in the Settings editor.

Prerequisites:
  ./myrm-dev ready --attach --chrome

Covers the `/intent/agent/<id>` landing route that links, shortcuts and notifications use:
  T1 - The route forwards to `/settings/agents?agentId=<id>` and the editor loads the agent it was given.
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
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    localStorage.setItem('myrm.proactive.dismissed.migration-discovery', 'forever');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

# Ready once the router has left /intent for the settings editor and the editor shows the requested agent.
_EDITOR_OPENED_JS = """(() => {
  const params = new URLSearchParams(location.search);
  const tab = document.querySelector('[data-testid="agent-tab-capabilities"]');
  const nameShown = (document.body?.innerText || '').includes(__NAME__)
    || Array.from(document.querySelectorAll('input')).some((input) => input.value === __NAME__);
  return {
    ready: location.pathname === '/settings/agents' && params.get('agentId') === __AGENT_ID__ && !!tab && nameShown,
    pathname: location.pathname,
    search: location.search,
    hasEditorTab: !!tab,
    nameShown,
    bodyLength: (document.body?.innerText || '').length,
  };
})()"""


def _create_agent(api_url: str, *, name: str) -> str:
    resp = http_json("POST", f"{api_url}/api/v1/user-agents", {"name": name})
    data = resp["data"]
    agent_id = data.get("id") or data.get("agent_id")
    assert isinstance(agent_id, str) and agent_id, json.dumps(data, ensure_ascii=False)
    return agent_id


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_agent_deep_link_opens_the_settings_editor() -> None:
    """`/intent/agent/<id>` lands on the Settings agent editor for exactly that agent."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    ui_url = get_e2e_ui_url().rstrip("/")

    name = f"deeplink-e2e-{uuid.uuid4().hex[:8]}"
    agent_id = _create_agent(api_url, name=name)
    try:
        warm_ui_route("/")
        with open_mcp_page(f"{ui_url}/intent/agent/{agent_id}", timeout_ms=120_000) as (client, page):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page)

            probe = _EDITOR_OPENED_JS.replace("__NAME__", json.dumps(name)).replace("__AGENT_ID__", json.dumps(agent_id))
            opened = wait_for_state(client, page, probe, timeout_sec=_warm_ui_parallel_wait_sec(120.0))
            assert opened.get("ready") is True, json.dumps(opened, ensure_ascii=False)
    finally:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
