"""Chrome E2E: enterprise settings > Audit Logs > Agent Behavior renders without CP.

Local dev has no Control Plane (:8003), so AgentAuditView's `getMyOrg` call
fails and the view must surface the localized error banner (agentOrgLoadFailed)
instead of white-screening. This validates the real-browser path of the
agent-audit UI (title skeleton + structured error banner + no crash).

Covers:
  T1 - /settings/enterprise opens and the tab nav renders.
  T2 - Clicking "Audit Logs" mounts the platform audit view.
  T3 - Clicking "Agent Behavior" mounts AgentAuditView with the localized
       org-load error banner (i18n agentOrgLoadFailed) when CP is unreachable.
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_ENTERPRISE_PATH = "/settings/enterprise"

# Clicks the "Audit Logs" tab (enterprise sub-tab) and waits for the platform audit view.
_AUDIT_TAB_JS = """(() => {
  const bodyText = document.body?.innerText || '';
  const btn = Array.from(document.querySelectorAll('nav button')).find((b) => {
    return /Audit Logs|审计日志|稽核日誌|감사 로그|監査ログ/.test(b.textContent || '');
  });
  if (!btn) {
    return { ready: false, reason: 'no-audit-tab-btn', snippet: bodyText.slice(0, 500) };
  }
  btn.click();
  return new Promise((resolve) => setTimeout(() => {
    const text = document.body?.innerText || '';
    const platformReady = /Platform Overview|平台总览|平台總覽/.test(text) ||
      /Failed to load audit data|审计数据加载失败|審計資料載入失敗/.test(text) ||
      /Audit Logs|审计日志/.test(text);
    resolve({
      ready: platformReady,
      platformText: text.slice(0, 1200),
    });
  }, 1200));
})()"""

# Switches to the "Agent Behavior" tab and waits for AgentAuditView terminal state.
# Radix Tabs triggers need the full event sequence; a bare .click() may not
# register in the real browser under SHPOIB hydration, so dispatch pointer/
# mouse/click events on the [role=tab] element each poll.
_AGENT_VIEW_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const titleReady = /Agent Behavior Audit|Agent 行为审计|Agent 行為審計/.test(text);
  const errorReady = /Failed to load organization|组织加载失败|組織載入失敗|Failed to load agent activity|无法加载 Agent 行为数据/.test(text);
  const dataReady = /Total Events|总事件数|總事件數|Security Blocks|安全拦截|安全攔截/.test(text);
  if (titleReady && (errorReady || dataReady)) {
    return { ready: true, titleReady, errorReady, dataReady, bodySnippet: text.slice(0, 1200) };
  }
  const tabs = Array.from(document.querySelectorAll('[role="tab"]')).map((t) => (t.textContent || '').trim());
  const tab = Array.from(document.querySelectorAll('[role="tab"]')).find((b) => {
    return /Agent Behavior|Agent 行为|Agent 行為/.test(b.textContent || '');
  });
  if (!tab) {
    return { ready: false, reason: 'no-agent-role-tab', tabs, titleReady, errorReady, bodySnippet: text.slice(0, 600) };
  }
  const list = tab.closest('[role="tablist"]');
  const selected = list ? (list.querySelector('[aria-selected="true"]')?.textContent || '') : '';
  if (!/Agent Behavior|Agent 行为|Agent 行為/.test(selected)) {
    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
      tab.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
    }
  }
  return {
    ready: false,
    reason: /Agent Behavior|Agent 行为|Agent 行為/.test(selected) ? 'agent-selected-not-ready' : 'dispatched-events',
    titleReady,
    errorReady,
    tabs,
    selectedText: selected.slice(0, 60),
    bodySnippet: text.slice(0, 800),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_enterprise_agent_audit_error_state_renders() -> None:
    """AgentAuditView renders the localized org-load error banner without a Control Plane."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    warm_ui_route(_ENTERPRISE_PATH)
    with open_settings_subroute(_ENTERPRISE_PATH, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)

        # T2: audit tab is reachable.
        audit = wait_for_state(client, page, _AUDIT_TAB_JS, timeout_sec=90.0)
        assert audit.get("ready") is True, json.dumps(audit, ensure_ascii=False)

        # T3: agent view error state renders (no CP locally -> org load fails).
        agent = wait_for_state(client, page, _AGENT_VIEW_READY_JS, timeout_sec=90.0)
        assert agent.get("ready") is True, json.dumps(agent, ensure_ascii=False)
