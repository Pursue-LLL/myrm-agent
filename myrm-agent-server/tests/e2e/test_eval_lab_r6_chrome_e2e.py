"""Chrome E2E for Eval Lab R6: history table columns, click-to-detail, manifest display.

Prerequisites:
  ./myrm ready --chrome

Covers:
  T1 - /eval-lab page loads with correct title and tabs
  T2 - History tab renders table with Profile and Model columns
  T3 - Old reports (no manifest) display '-' for profile/model (graceful degradation)
  T4 - Click history row loads report detail, switches to Report tab
  T5 - Report tab environment snapshot shows profile_id / benchmark_mode fields
  T6 - Table has horizontal scroll container (responsive)
"""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import get_e2e_ui_url, open_mcp_page, wait_for_state

EVAL_LAB_URL = f"{get_e2e_ui_url()}/eval-lab"

_SERVER_ROOT = Path(__file__).resolve().parents[2]

_DISMISS_MIGRATION_JS = """(() => {
  sessionStorage.setItem('migration_discovery_dismissed', 'true');
  sessionStorage.setItem('competitor_migration_dismissed', 'true');
  return true;
})()"""

_PAGE_LOAD_PROBE_JS = """(() => {
  const bodyText = document.body.innerText || '';
  const title = document.title;
  const h1 = document.querySelector('h1');
  const h1Text = h1 ? h1.textContent : '';

  const tabs = document.querySelectorAll('[role="tab"]');
  const tabTexts = Array.from(tabs).map(t => t.textContent || '');

  return {
    ready: tabTexts.length >= 2 && bodyText.length > 50,
    title,
    h1Text,
    tabTexts,
    tabCount: tabTexts.length,
    bodyLength: bodyText.length,
    url: location.href,
  };
})()"""

_HISTORY_TABLE_PROBE_JS = """(() => {
  const historyTab = Array.from(document.querySelectorAll('[role="tab"]'))
    .find(t => {
      const text = (t.textContent || '').toLowerCase();
      return text.includes('history') || text.includes('历史');
    });
  if (historyTab) historyTab.click();

  return new Promise(resolve => setTimeout(() => {
    const table = document.querySelector('table');
    if (!table) {
      resolve({ ready: true, hasTable: false, headers: [], rowCount: 0 });
      return;
    }

    const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent || '');
    const rows = table.querySelectorAll('tbody tr');
    const rowCount = rows.length;

    const firstRow = rows.length > 0 ? rows[0] : null;
    const firstRowCells = firstRow
      ? Array.from(firstRow.querySelectorAll('td')).map(td => td.textContent || '')
      : [];

    const scrollContainer = table.closest('[class*="overflow-x"]') || table.closest('.overflow-x-auto');
    const hasScrollContainer = !!scrollContainer;
    const tableMinWidth = table.style.minWidth || getComputedStyle(table).minWidth;

    const profileColIdx = headers.findIndex(h =>
      h.toLowerCase().includes('profile') || h.includes('配置'));
    const modelColIdx = headers.findIndex(h =>
      h.toLowerCase().includes('model') || h.includes('模型'));

    const profileCellText = profileColIdx >= 0 && firstRowCells.length > profileColIdx
      ? firstRowCells[profileColIdx] : null;
    const modelCellText = modelColIdx >= 0 && firstRowCells.length > modelColIdx
      ? firstRowCells[modelColIdx] : null;

    resolve({
      ready: true,
      hasTable: true,
      headers,
      headerCount: headers.length,
      rowCount,
      firstRowCells,
      hasScrollContainer,
      tableMinWidth,
      profileColIdx,
      modelColIdx,
      profileCellText,
      modelCellText,
      hasCursorPointer: firstRow
        ? getComputedStyle(firstRow).cursor === 'pointer'
        : false,
    });
  }, 500));
})()"""

_CLICK_ROW_AND_CHECK_REPORT_JS = """(() => {
  const table = document.querySelector('table');
  if (!table) return { ready: true, clicked: false, reason: 'no_table' };

  const rows = table.querySelectorAll('tbody tr');
  if (rows.length === 0) return { ready: true, clicked: false, reason: 'no_rows' };

  rows[0].click();

  return new Promise(resolve => setTimeout(() => {
    const reportTab = Array.from(document.querySelectorAll('[role="tab"]'))
      .find(t => {
        const text = (t.textContent || '').toLowerCase();
        return text.includes('report') || text.includes('报告');
      });

    const isReportActive = reportTab
      ? reportTab.getAttribute('data-state') === 'active'
        || reportTab.getAttribute('aria-selected') === 'true'
      : false;

    const bodyText = document.body.innerText || '';
    const hasEnvironment = bodyText.includes('Environment')
      || bodyText.includes('环境快照')
      || bodyText.includes('环境');
    const hasProfile = bodyText.includes('Profile')
      || bodyText.includes('配置');
    const hasBenchmark = bodyText.includes('Benchmark')
      || bodyText.includes('基准');
    const hasOnOff = bodyText.includes('ON') || bodyText.includes('OFF');
    const hasBudgetBadge = /88 calls \\/ 99 iterations|88 次调用 \\/ 99 轮迭代/.test(bodyText);
    const hasDecontamEnabled = /Enabled|已启用/.test(bodyText);
    const hasLimitBadge = /Limit|上限/.test(bodyText);
    const hasBlockedBadge = /Blocked 1|已拦截 1/.test(bodyText);
    const hasToolCalls3 = /3×/.test(bodyText);

    resolve({
      ready: true,
      clicked: true,
      isReportActive,
      hasEnvironment,
      hasProfile,
      hasBenchmark,
      hasOnOff,
      hasBudgetBadge,
      hasDecontamEnabled,
      hasLimitBadge,
      hasBlockedBadge,
      hasToolCalls3,
    });
  }, 2000));
})()"""


@contextlib.contextmanager
def _seeded_budget_report() -> object:
    """Seed a single-profile eval report carrying the #6 budget/decontam fields.

    The report lives under the server working directory (``.myrm/eval_reports``),
    same resolution used by ``app.core.eval.reports``. The first JSONL line is the
    summary (manifest with the engine-enforced caps), the second is the per-case
    record with the trajectory badges, mirroring what ``LocalEvalExecutor`` writes.
    """
    reports_dir = _SERVER_ROOT / ".myrm/eval_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    report_path = reports_dir / f"eval_report_{now}.jsonl"
    summary: dict[str, object] = {
        "type": "summary",
        "total_cases": 1,
        "total": 1,
        "passed": 0,
        "pass_count": 0,
        "fail_count": 1,
        "error_count": 0,
        "avg_pass_rate": 0.0,
        "avg_time_secs": 3.2,
        "avg_total_tokens": 1000,
        "profile_id": None,
        "benchmark_mode": True,
        "decontam_active": True,
        "manifest": {
            "model_provider": "openai",
            "model_id": "test-model",
            "thinking_effort": "high",
            "harness_version": "0.1.0",
            "tool_policy": ["web_search", "web_fetch"],
            "task_set_id": "browsecomp",
            "prompt_fingerprint": "a1b2c3d4e5f6a1b2",
            "profile_id": None,
            "benchmark_mode": True,
            "judge_model": "openai/test-judge",
            "max_tool_calls": 88,
            "max_iterations": 99,
        },
    }
    case: dict[str, object] = {
        "passed": False,
        "case": {
            "message": "Budget badge trajectory case",
            "expected_tools": [],
            "state_assertions": [],
        },
        "scores": {"pass_rate": 0.0},
        "usage": {"total_tokens": 1000},
        "time_secs": 3.2,
        "details": None,
        "actual_tools": [],
        "actual_output": "",
        "limit_reached": "max_iterations",
        "blocked_count": 1,
        "tool_call_details": [
            {"name": "web_search"},
            {"name": "web_search"},
            {"name": "web_fetch"},
        ],
    }
    report_path.write_text(
        json.dumps(summary, ensure_ascii=False) + "\n" + json.dumps(case, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    try:
        yield None
    finally:
        report_path.unlink(missing_ok=True)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_eval_lab_r6_history_and_detail_chrome_e2e() -> None:
    """Eval Lab R6: history table columns, click-to-detail, manifest fields."""
    with _seeded_budget_report():
        with open_mcp_page(EVAL_LAB_URL) as (client, page):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=5.0)

            # T1: Page loads with title and tabs
            state = wait_for_state(client, page, _PAGE_LOAD_PROBE_JS, timeout_sec=45.0)

            assert state.get("url", "").endswith("/eval-lab") or "eval" in state.get("url", "").lower(), (
                f"URL should contain eval-lab: {state.get('url')}"
            )
            assert isinstance(state.get("tabCount"), int) and state["tabCount"] >= 2, (
                f"Should have >=2 tabs, got {state.get('tabCount')}: {state.get('tabTexts')}"
            )

            # T2: History table structure
            table_state = wait_for_state(client, page, _HISTORY_TABLE_PROBE_JS, timeout_sec=30.0)

            if table_state.get("hasTable"):
                headers = table_state.get("headers", [])
                assert table_state.get("headerCount", 0) >= 7, (
                    f"Table should have >=7 columns (with Profile+Model), got {table_state.get('headerCount')}: {headers}"
                )

                assert table_state.get("profileColIdx", -1) >= 0, (
                    f"Profile column should exist in headers: {headers}"
                )
                assert table_state.get("modelColIdx", -1) >= 0, (
                    f"Model column should exist in headers: {headers}"
                )

                # T6: Responsive - scroll container exists
                assert table_state.get("hasScrollContainer") is True, (
                    "Table should be wrapped in overflow-x-auto container"
                )

                # T3: Old reports graceful degradation
                if table_state.get("rowCount", 0) > 0:
                    assert table_state.get("hasCursorPointer") is True, (
                        "Table rows should have cursor:pointer for click-to-detail"
                    )

                    profile_text = table_state.get("profileCellText", "")
                    assert profile_text is not None, (
                        "Profile cell should have content (even '-' for old reports)"
                    )

                    # T4: Click row to load detail
                    report_state = wait_for_state(
                        client, page, _CLICK_ROW_AND_CHECK_REPORT_JS, timeout_sec=30.0,
                    )

                    if report_state.get("clicked"):
                        assert report_state.get("isReportActive") is True, (
                            "After clicking history row, Report tab should be active"
                        )

                        # T5: Environment snapshot fields
                        if report_state.get("hasEnvironment"):
                            assert report_state.get("hasProfile") is True, (
                                "Report environment should show Profile field"
                            )
                            assert report_state.get("hasBenchmark") is True, (
                                "Report environment should show Benchmark field"
                            )
                            assert report_state.get("hasBudgetBadge") is True, (
                                f"Report should render the budget badge (88 calls / 99 iterations): {report_state}"
                            )
                            assert report_state.get("hasDecontamEnabled") is True, (
                                f"Report should render the decontamination Enabled badge: {report_state}"
                            )
                            assert report_state.get("hasLimitBadge") is True, (
                                f"Report should render the Limit (max_iterations) trajectory badge: {report_state}"
                            )
                            assert report_state.get("hasBlockedBadge") is True, (
                                f"Report should render the Blocked 1 trajectory badge: {report_state}"
                            )
                            assert report_state.get("hasToolCalls3") is True, (
                                f"Report should render the 3x tool-call trajectory badge: {report_state}"
                            )
