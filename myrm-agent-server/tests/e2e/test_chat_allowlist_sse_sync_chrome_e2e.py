"""Chrome READ E2E: agent_config_updated SSE refreshes bound chat allowlist."""

from __future__ import annotations

import json
import time
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    warm_ui_route,
)
from tests.support.chrome_openapi_fail_loud_e2e import apply_agent_from_e2e_api_js

_SKILL_A = "code-review"
_SKILL_B = "systematic-debugging"


def _create_agent_with_skill(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    created = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        {
            "name": f"Allowlist SSE E2E {suffix}",
            "description": "Chat allowlist SSE sync probe",
            "system_prompt": "Test agent.",
            "mcp_ids": [],
            "skill_ids": [_SKILL_A],
            "enabled_builtin_tools": ["web_search", "memory"],
        },
    )
    agent_id = created.get("data", {}).get("id") if isinstance(created.get("data"), dict) else created.get("id")
    assert isinstance(agent_id, str) and agent_id
    return agent_id


def _delete_agent(api_url: str, agent_id: str) -> None:
    try:
        http_json(
            "DELETE",
            f"{api_url}/api/v1/user-agents/{agent_id}",
            expected_statuses=frozenset({200, 204}),
        )
    except RuntimeError:
        pass


_ALLOWLIST_COUNT_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  return {
    count: snap.agentSelectedSkillCount ?? 0,
    agentId: window.__myrmChatStore?.getState?.()?.agentConfig?.agentId ?? null,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_agent_profile_update_sse_syncs_bound_chat_skill_allowlist() -> None:
    """When server emits agent_config_updated, chat store selectedSkillIds match API."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url().rstrip("/")
    prepare_e2e_ui_session(api_url)
    warm_ui_route("/")
    agent_id = _create_agent_with_skill(api_url)

    try:
        with open_mcp_page(f"{ui_url}/", timeout_ms=120_000) as (client, page):
            wait_for_react_e2e_bridge(client, page, timeout_sec=90.0)
            applied = client.evaluate(page, apply_agent_from_e2e_api_js(agent_id), timeout_sec=60.0)
            assert isinstance(applied, dict) and applied.get("ok") is True, applied

            baseline = client.evaluate(page, _ALLOWLIST_COUNT_JS, timeout_sec=15.0)
            assert baseline.get("count") == 1, baseline

            http_json(
                "PUT",
                f"{api_url}/api/v1/user-agents/{agent_id}",
                {"skill_ids": [_SKILL_A, _SKILL_B]},
            )

            deadline = time.monotonic() + 20.0
            synced: dict[str, object] = {"count": 0}
            while time.monotonic() < deadline:
                raw = client.evaluate(page, _ALLOWLIST_COUNT_JS, timeout_sec=15.0)
                synced = raw if isinstance(raw, dict) else {"count": 0}
                if synced.get("count") == 2:
                    break
                time.sleep(0.5)
            assert synced.get("count") == 2, synced
    finally:
        _delete_agent(api_url, agent_id)
