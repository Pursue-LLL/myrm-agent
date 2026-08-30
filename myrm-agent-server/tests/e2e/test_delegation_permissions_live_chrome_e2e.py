"""Chrome LIVE E2E: explore preset blocks external CLI via WebUI same-origin agent-stream."""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    warm_ui_route,
)


def _seed_explore_fixture(api_url: str) -> dict[str, str]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-security-preset-fixture")
    assert isinstance(seeded, dict)
    explore_chat_id = str(seeded.get("explore_chat_id") or "")
    assert explore_chat_id.startswith("e2esecpreset")
    assert str(seeded.get("explore_ui_path") or "").startswith("/")
    payload = {key: str(seeded[key]) for key in seeded}
    # Chat-bound routes hydrate agentConfig via loadMessages (more reliable than ?agentId= alone).
    payload["explore_ui_path"] = f"/{payload['explore_chat_id']}"
    return payload


_EXPLORE_FORCE_EXTERNAL_BLOCK_JS = """(async () => {
  const chatId = `e2e-explore-ext-block-${Date.now()}`;
  const body = {
    query: 'Run external CLI task',
    message_id: `msg-${chatId}`,
    chat_id: chatId,
    action_mode: 'agent',
    security_preset: 'explore',
    force_external_agent: 'echo-cli',
    agent_config: { enabled_builtin_tools: ['external_cli'], skill_ids: [] },
    timezone: 'UTC',
  };

  const res = await fetch('/api/v1/agents/agent-stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  const denied =
    /external agent delegation denied/i.test(text) ||
    /invoke_external_agent denied/i.test(text);
  const delegated = /delegate:|delegation_/i.test(text);
  return {
    ok: denied && !delegated,
    denied,
    delegated,
    status: res.status,
    sample: text.slice(0, 2500),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_explore_preset_blocks_force_external_via_webui_agent_stream() -> None:
    """Lane-C Chrome LIVE: same-origin agent-stream with explore+force_external must deny."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_explore_fixture(api_url)
    explore_path = seeded["explore_ui_path"]

    warm_ui_route(explore_path)
    with open_mcp_page(f"{ui_url}{explore_path}", timeout_ms=120_000) as (client, page):
        result = client.evaluate(page, _EXPLORE_FORCE_EXTERNAL_BLOCK_JS, timeout_sec=120.0)
        assert isinstance(result, dict), result
        assert result.get("ok") is True, json.dumps(result, ensure_ascii=False)
