"""Real Chrome MCP E2E: Channel routing dropdown excludes Search-track agents."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_BLOCKED_SEARCH_IDS = frozenset({"builtin-fast-search", "builtin-deep-search"})

_ROUTING_AGENT_OPTIONS_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  const onChannels = location.pathname.includes('/settings/channels');
  if (!onChannels) {
    return { ready: false, reason: 'not-on-channels' };
  }
  const navButtons = Array.from(document.querySelectorAll('button'));
  const routingTab = navButtons.find((el) =>
    /Channel Routing|渠道路由/i.test(el.textContent || '')
  );
  if (routingTab) {
    routingTab.click();
  }
  const channelBtn = navButtons.find((el) =>
    /^(webhook|chat)$/i.test((el.textContent || '').trim())
  );
  if (channelBtn) {
    channelBtn.click();
  }
  const selects = Array.from(document.querySelectorAll('select'));
  const options = selects.flatMap((select) =>
    Array.from(select.options).map((option) => ({
      value: option.value,
      text: option.textContent || '',
    }))
  );
  const hasGlobalAgent = /Global Default Agent|全局默认/i.test(bodyText);
  const ready =
    onChannels &&
    (/Channel Routing|渠道路由/i.test(bodyText) || !!routingTab) &&
    selects.length > 0 &&
    options.length > 1;
  return {
    ready,
    hasGlobalAgent,
    selectCount: selects.length,
    optionValues: options.map((item) => item.value),
    optionTexts: options.map((item) => item.text),
    bodySnippet: bodyText.slice(0, 400),
  };
})()"""


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_channel_routing_dropdown_excludes_search_agents() -> None:
    """Settings → Channel Routing → agent selects must not list Search presets."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/settings/channels?sub=routing")
    with open_mcp_page(
        f"{ui_url}/settings/channels?sub=routing", timeout_ms=90_000
    ) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        state = wait_for_state(
            client,
            page,
            _ROUTING_AGENT_OPTIONS_STATE,
            timeout_sec=90.0,
        )
        assert state.get("ready") is True, state
        option_values = state.get("optionValues")
        assert isinstance(option_values, list), state
        blocked = [value for value in option_values if value in _BLOCKED_SEARCH_IDS]
        assert (
            blocked == []
        ), f"Search agents must not appear in channel routing UI: {blocked}"
        search_like = [
            value
            for value in option_values
            if isinstance(value, str)
            and ("search" in value.lower() and value not in ("", "none"))
        ]
        assert not any(item in _BLOCKED_SEARCH_IDS for item in search_like), state
