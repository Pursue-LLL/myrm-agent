"""Real Chrome MCP E2E for Memory Command Center doctor panel.

Covers the real-user flow on the settings memory page:

1. Open /settings/memory and confirm the Memory Doctor panel renders with a
   "Run all diagnostics" action available.
2. Click the action and wait for the diagnostic run to complete (latest result
   section appears with Recall@k).
3. Confirm the benchmark trend section renders latency p50/p95 once at least
   two benchmarked runs exist (the test pre-seeds one run via the same API the
   UI uses, so the trend section deterministically appears after the click).

The embedding-backed golden recall benchmark runs against the real dev stack;
no critical path is mocked.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)

_OPEN_VERIFY_TAB_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => {
      const label = (el.textContent || '').trim();
      return /^(验证|Verify)$/.test(label);
    },
  );
  if (!btn) return { ready: false, clicked: false };
  btn.click();
  return { ready: true, clicked: true };
})()"""

_DOCTOR_PANEL_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const hasTitle = /Run memory diagnostics|运行记忆诊断/.test(text);
  const runBtn = Array.from(document.querySelectorAll('button')).find(
    (el) => /Run all diagnostics|运行全部诊断/.test(el.textContent || ''),
  );
  return { ready: hasTitle && !!runBtn, hasTitle, hasRunBtn: !!runBtn, text: text.slice(0, 800) };
})()"""

_CLICK_RUN_DIAGNOSTICS_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => /Run all diagnostics|运行全部诊断/.test(el.textContent || ''),
  );
  if (!btn || btn.disabled) return { ready: false, clicked: false, disabled: btn?.disabled ?? null };
  btn.click();
  return { ready: true, clicked: true };
})()"""

_DIAGNOSTIC_RESULT_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const hasLastRun = /Latest diagnostic result|最近诊断结果/.test(text);
  const hasRecall = /Recall@\\d+|召回率@\\d+|Recall|召回率/.test(text);
  const runBtnDisabled = !!Array.from(document.querySelectorAll('button')).find(
    (el) => /Run all diagnostics|运行全部诊断/.test(el.textContent || '') && el.disabled,
  );
  return {
    ready: hasLastRun && hasRecall && !runBtnDisabled,
    hasLastRun,
    hasRecall,
    runBtnDisabled,
    text: text.slice(0, 1200),
  };
})()"""

_TREND_SECTION_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const hasTrend = /Benchmark trend|基准趋势/.test(text);
  const hasP50 = /Latency P50|延迟 P50/.test(text);
  const hasP95 = /Latency P95|延迟 P95/.test(text);
  const hasMs = /\\d+ms/.test(text);
  return {
    ready: hasTrend && hasP50 && hasP95 && hasMs,
    hasTrend,
    hasP50,
    hasP95,
    hasMs,
    text: text.slice(0, 1400),
  };
})()"""


@contextmanager
def _memory_doctor_panel() -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    api_url = get_e2e_api_url()
    # Pre-seed one benchmarked run so the trend section deterministically shows
    # after the UI-triggered run below (it needs at least two runs).
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/memory/command-center/diagnostics/actions",
        body={"action": "run_diagnostics"},
    )
    assert isinstance(seeded, dict), seeded
    assert seeded.get("run", {}).get("probes"), seeded

    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (client, page):
        yield client, page


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_doctor_panel_run_and_latency_trend_chrome_e2e() -> None:
    """Real user flow: open doctor panel, run diagnostics, verify latency trend."""
    with _memory_doctor_panel() as (client, page):
        opened = wait_for_state(client, page, _OPEN_VERIFY_TAB_JS, timeout_sec=60.0)
        assert opened.get("clicked") is True, opened

        panel = wait_for_state(client, page, _DOCTOR_PANEL_READY_JS, timeout_sec=90.0)
        assert panel.get("ready") is True, panel

        clicked = wait_for_state(client, page, _CLICK_RUN_DIAGNOSTICS_JS, timeout_sec=30.0)
        assert clicked.get("clicked") is True, clicked

        result = wait_for_state(client, page, _DIAGNOSTIC_RESULT_READY_JS, timeout_sec=180.0)
        assert result.get("ready") is True, result

        trend = wait_for_state(client, page, _TREND_SECTION_READY_JS, timeout_sec=90.0)
        assert trend.get("ready") is True, trend


_OPEN_ACT_TAB_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => {
      const label = (el.textContent || '').trim();
      return /^(治理|Act)$/.test(label);
    },
  );
  if (!btn) return { ready: false, clicked: false };
  btn.click();
  return { ready: true, clicked: true };
})()"""

_TOOL_GUIDANCE_PANEL_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const hasTitle = /工具使用指南与自适应避坑/.test(text);
  const hasAdaptiveBadge = /智能自适应/.test(text);
  const hasDesc = /自动沉淀工具调用踩坑经验/.test(text);
  const hasMetrics = /活跃工具/.test(text) && /避坑经验/.test(text);
  const refreshBtn = Array.from(document.querySelectorAll('button')).find(
    (el) => /刷新/.test(el.textContent || ''),
  );
  return {
    ready: hasTitle && hasAdaptiveBadge && hasDesc && hasMetrics && !!refreshBtn,
    hasTitle,
    hasAdaptiveBadge,
    hasDesc,
    hasMetrics,
    hasRefreshBtn: !!refreshBtn,
    text: text.slice(0, 800),
  };
})()"""

_CLICK_REFRESH_TOOL_GUIDANCE_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => /刷新/.test(el.textContent || ''),
  );
  if (!btn || btn.disabled) return { ready: false, clicked: false };
  btn.click();
  return { ready: true, clicked: true };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_tool_guidance_panel_chrome_e2e() -> None:
    """Real user flow: open memory command center, switch to Act tab, verify Tool Guidance panel renders & refresh works."""
    with _memory_doctor_panel() as (client, page):
        opened = wait_for_state(client, page, _OPEN_ACT_TAB_JS, timeout_sec=60.0)
        assert opened.get("clicked") is True, opened

        panel = wait_for_state(client, page, _TOOL_GUIDANCE_PANEL_READY_JS, timeout_sec=90.0)
        assert panel.get("ready") is True, panel

        refreshed = wait_for_state(client, page, _CLICK_REFRESH_TOOL_GUIDANCE_JS, timeout_sec=30.0)
        assert refreshed.get("clicked") is True, refreshed


_OPEN_UNDERSTAND_TAB_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => {
      const label = (el.textContent || '').trim();
      return /^(理解|Understand)$/.test(label);
    },
  );
  if (!btn) return { ready: false, clicked: false };
  btn.click();
  return { ready: true, clicked: true };
})()"""

_ECONOMICS_PANEL_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const hasTitle = /长程记忆经济学剖析器|Memory Economics Profiler/i.test(text);
  const hasTrajectories = /长程轮次记忆装载与时序轨迹|Turn Trajectories/i.test(text);
  const refreshBtn = Array.from(document.querySelectorAll('button')).find(
    (el) => /刷新分析|Refresh Analysis/i.test(el.textContent || ''),
  );
  return {
    ready: hasTitle && hasTrajectories && !!refreshBtn,
    hasTitle,
    hasTrajectories,
    hasRefreshBtn: !!refreshBtn,
    text: text.slice(0, 1000),
  };
})()"""

_CLICK_REFRESH_ECONOMICS_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => /刷新分析|Refresh Analysis/i.test(el.textContent || ''),
  );
  if (!btn || btn.disabled) return { ready: false, clicked: false };
  btn.click();
  return { ready: true, clicked: true };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_economics_panel_chrome_e2e() -> None:
    """Real user flow: open memory command center, switch to Understand tab, verify Memory Economics panel renders & refresh works."""
    with _memory_doctor_panel() as (client, page):
        opened = wait_for_state(client, page, _OPEN_UNDERSTAND_TAB_JS, timeout_sec=60.0)
        assert opened.get("clicked") is True, opened

        panel = wait_for_state(client, page, _ECONOMICS_PANEL_READY_JS, timeout_sec=90.0)
        assert panel.get("ready") is True, panel

        refreshed = wait_for_state(client, page, _CLICK_REFRESH_ECONOMICS_JS, timeout_sec=30.0)
        assert refreshed.get("clicked") is True, refreshed



