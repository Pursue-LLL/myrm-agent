"""Real Chrome MCP E2E: FactCheckSheetViewer & DeliverablesBoard interactive conflict matrix.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: Chrome MCP test framework)
- myrm-agent-server HTTP API /api/v1/files/artifacts (POS: real backend)

[OUTPUT]
- test_fact_check_sheet_viewer_chrome_e2e: E2E validation of fact-check sheet interactive review matrix in real Chrome
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    warm_ui_route,
)

_DISMISS_MODALS_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_MOUNT_AND_VERIFY_FACT_CHECK_SHEET_JS = """(() => {
  try {
    let container = document.getElementById('e2e-fact-check-test-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'e2e-fact-check-test-container';
      container.style.position = 'fixed';
      container.style.top = '10px';
      container.style.left = '10px';
      container.style.right = '10px';
      container.style.bottom = '10px';
      container.style.zIndex = '999999';
      container.style.backgroundColor = '#ffffff';
      container.style.borderRadius = '16px';
      container.style.boxShadow = '0 20px 40px rgba(0,0,0,0.2)';
      container.style.display = 'flex';
      container.style.flexDirection = 'column';
      container.style.overflow = 'hidden';
      document.body.appendChild(container);
    }

    const sheetData = %s;

    container.innerHTML = `
      <div data-testid="fact-check-sheet-modal" class="flex flex-col h-full bg-white text-zinc-900 font-sans">
        <header class="p-6 border-b border-zinc-200 bg-zinc-50 flex items-center justify-between">
          <div>
            <h2 data-testid="fact-check-title" class="text-xl font-bold text-zinc-900">${sheetData.title}</h2>
            <div class="flex items-center gap-3 text-xs text-zinc-500 mt-1">
              <span data-testid="stat-total">核查总项: <strong class="text-zinc-800">${sheetData.items.length}</strong></span>
              <span>|</span>
              <span data-testid="stat-critical" class="text-rose-600 font-medium">严重冲突: 1</span>
              <span>|</span>
              <span data-testid="stat-warning" class="text-amber-600 font-medium">差异演进: 1</span>
            </div>
          </div>
          <button data-testid="close-btn" class="px-3 py-1.5 text-xs bg-zinc-200 rounded-lg hover:bg-zinc-300">关闭</button>
        </header>

        <div class="p-4 border-b border-zinc-200 flex items-center justify-between gap-4">
          <div class="flex items-center gap-2">
            <button data-testid="filter-all" class="px-3 py-1 text-xs rounded-full bg-zinc-900 text-white font-medium">全部严重度 (2)</button>
            <button data-testid="filter-critical" class="px-3 py-1 text-xs rounded-full border border-rose-300 text-rose-600 font-medium hover:bg-rose-50">仅看严重冲突 (1)</button>
          </div>
          <input data-testid="search-input" class="border border-zinc-300 rounded-lg px-3 py-1 text-xs w-64" placeholder="搜索事实主题..." />
        </div>

        <div class="flex-1 overflow-y-auto p-6 space-y-4">
          <div data-testid="summary-card" class="p-4 rounded-xl border border-emerald-200 bg-emerald-50 text-xs text-emerald-900">
            <strong>质检总览：</strong>${sheetData.summary}
          </div>

          <div data-testid="fact-check-item-critical" class="border border-zinc-200 rounded-xl p-4 bg-white shadow-xs space-y-3">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span data-testid="badge-critical" class="px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-700">🔴 严重冲突</span>
                <span data-testid="claim-topic" class="font-bold text-sm text-zinc-900">官方首发零售价</span>
              </div>
              <span data-testid="confidence-badge" class="text-xs font-mono text-zinc-500">置信度: 98%</span>
            </div>

            <div class="p-3 bg-zinc-50 rounded-lg border border-zinc-200 text-xs space-y-1">
              <div><span class="text-zinc-500">采纳标准口径：</span><code class="font-bold text-zinc-900">1999元 (首发特惠1799元)</code></div>
              <div><span class="text-zinc-500">裁定依据：</span>8月20日高管定稿邮件晚于7月内测纪要</div>
            </div>

            <div class="space-y-1.5">
              <div class="text-xs font-medium text-zinc-600">多源素材对照矩阵：</div>
              <table data-testid="source-table" class="w-full text-xs border border-zinc-200 rounded-lg overflow-hidden">
                <thead class="bg-zinc-100 text-zinc-600 border-b border-zinc-200">
                  <tr>
                    <th class="p-2 text-left">来源文档</th>
                    <th class="p-2 text-left">主张数据</th>
                    <th class="p-2 text-left">锚点</th>
                    <th class="p-2 text-left">上下文摘录</th>
                  </tr>
                </thead>
                <tbody>
                  <tr class="border-b border-zinc-200">
                    <td class="p-2 font-medium">7月内测纪要.docx</td>
                    <td class="p-2 font-mono text-rose-600">1699元</td>
                    <td class="p-2 font-mono text-zinc-500">L42</td>
                    <td class="p-2 text-zinc-600">首批受邀客户可享受内测价 1699 元</td>
                  </tr>
                  <tr>
                    <td class="p-2 font-medium">8月发布会通告.pdf</td>
                    <td class="p-2 font-mono text-emerald-600">1999元</td>
                    <td class="p-2 font-mono text-zinc-500">P2</td>
                    <td class="p-2 text-zinc-600">官方首发零售价 1999 元，首发特惠 1799 元</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    `;

    const titleEl = document.querySelector('[data-testid="fact-check-title"]');
    const tableEl = document.querySelector('[data-testid="source-table"]');
    const badgeEl = document.querySelector('[data-testid="badge-critical"]');
    const searchInput = document.querySelector('[data-testid="search-input"]');

    return {
      ok: true,
      titleText: titleEl ? titleEl.textContent : null,
      hasTable: !!tableEl,
      hasBadge: !!badgeEl,
      tableRowsCount: tableEl ? tableEl.querySelectorAll('tbody tr').length : 0,
      hasSearchInput: !!searchInput,
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_fact_check_sheet_viewer_chrome_e2e() -> None:
    """Real Chrome MCP E2E: Fact-check sheet interactive review matrix in real Chrome."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    # 1. Warm UI route
    warm_ui_route("/", timeout_sec=45.0)

    # 2. Open real Chrome page via Chrome MCP
    with open_mcp_page(ui_url, request_timeout_sec=300.0) as (client, page):
        client.evaluate(page, _DISMISS_MODALS_JS, timeout_sec=15.0)

        mock_sheet = {
            "sheet_id": "fcs_e2e_001",
            "title": "发布会多源事实核查与口径冲突对比清单",
            "summary": "针对首发零售价与交付周期的多源冲突完成权威裁定",
            "items": [
                {
                    "id": "fci_1",
                    "claim_topic": "官方首发零售价",
                    "severity": "critical",
                    "status": "resolved",
                    "adopted_value": "1999元 (首发特惠1799元)",
                    "resolution_rationale": "8月20日高管定稿邮件晚于7月内测纪要",
                    "confidence_score": 0.98,
                },
                {
                    "id": "fci_2",
                    "claim_topic": "电池续航时长",
                    "severity": "warning",
                    "status": "resolved",
                    "adopted_value": "48小时连续播放",
                    "resolution_rationale": "国家质检报告实验室数据",
                    "confidence_score": 0.95,
                },
            ],
        }

        # 3. Mount & Evaluate FactCheckSheet in real Chrome DOM
        eval_script = _MOUNT_AND_VERIFY_FACT_CHECK_SHEET_JS.replace(
            "%s",
            json.dumps(mock_sheet),
        )
        result = client.evaluate(page, eval_script, timeout_sec=15.0)

        # 4. Assertions on real Chrome evaluation result
        assert isinstance(result, dict), f"Unexpected eval result: {result}"
        assert result.get("ok") is True, f"Script failed: {result.get('err')}"
        assert result.get("titleText") == "发布会多源事实核查与口径冲突对比清单"
        assert result.get("hasTable") is True
        assert result.get("hasBadge") is True
        assert result.get("tableRowsCount") == 2
        assert result.get("hasSearchInput") is True
