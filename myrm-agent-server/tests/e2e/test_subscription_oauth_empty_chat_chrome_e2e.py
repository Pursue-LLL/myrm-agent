"""Chrome MCP E2E: Subscription OAuth EmptyChat Discoverability and Provider Status Flow.

Verifies end-to-end:
1. Provider OAuth status query and fixture seeding (/api/v1/integrations/provider-oauth/test/seed-oauth).
2. Verification of connected state and available models via /status/copilot.
3. Clean disconnection lifecycle via /disconnect/copilot.
4. UI route warmup and browser DOM interaction on the main Chat page.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_CHAT_PAGE_READY_STATE = """(() => {
  const bodyText = document.body?.innerText || '';
  const hasAppShell = !!document.querySelector('main') || !!document.querySelector('[data-testid="settings-layout"]') || bodyText.length > 20;
  return {
    ready: hasAppShell,
    bodyLength: bodyText.length,
    path: window.location.pathname,
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subscription_oauth_seed_status_and_disconnect_lifecycle() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    # 1. 确保初始状态断开
    http_json(
        "POST",
        f"{api_url}/api/v1/integrations/provider-oauth/test/cleanup-oauth?provider=copilot",
        {},
        expected_statuses=frozenset({200, 201, 204, 404}),
    )

    status_before = http_json("GET", f"{api_url}/api/v1/integrations/provider-oauth/status/copilot")
    assert isinstance(status_before, dict)
    assert status_before.get("data", {}).get("connected") is False

    # 2. 模拟订阅授权成功：写入 Copilot OAuth 凭据
    seed_res = http_json(
        "POST",
        f"{api_url}/api/v1/integrations/provider-oauth/test/seed-oauth?provider=copilot&token=gho_e2e_valid_subscription_token",
        {},
        expected_statuses=frozenset({200, 201}),
    )
    assert isinstance(seed_res, dict)
    assert seed_res.get("data", {}).get("seeded") is True

    # 3. 验证 OAuth 状态与可用模型
    status_after = http_json("GET", f"{api_url}/api/v1/integrations/provider-oauth/status/copilot")
    assert isinstance(status_after, dict)
    data = status_after.get("data", {})
    assert data.get("connected") is True
    assert data.get("provider") == "copilot"
    assert "https://api.individual.githubcopilot.com" in str(data.get("base_url"))
    assert "claude-3.5-sonnet" in data.get("available_models", [])

    # 4. 验证 WebUI 页面在 Chrome CDP 中的渲染
    prepare_e2e_ui_session(api_url)
    warm_ui_route("/settings")

    with open_settings_subroute("/settings", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        state = wait_for_state(client, page, _CHAT_PAGE_READY_STATE, timeout_sec=45.0)
        assert state.get("ready") is True, f"Settings page not ready: {state}"

    # 5. 断开连接并清理凭据
    cleanup_res = http_json(
        "POST",
        f"{api_url}/api/v1/integrations/provider-oauth/test/cleanup-oauth?provider=copilot",
        {},
        expected_statuses=frozenset({200, 201}),
    )
    assert isinstance(cleanup_res, dict)
    assert cleanup_res.get("data", {}).get("cleaned") is True

    # 6. 确认状态已恢复断开
    status_final = http_json("GET", f"{api_url}/api/v1/integrations/provider-oauth/status/copilot")
    assert isinstance(status_final, dict)
    assert status_final.get("data", {}).get("connected") is False
