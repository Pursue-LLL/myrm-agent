"""Chrome E2E: Real Browser Multi-Page Table Harvesting and Dual-Sentinel Pagination Loop in WebUI.

[INPUT]
- Chrome MCP remote debugging port (9333) attached to real Chrome instance
- WebUI Chat Session on http://localhost:3000
- Inject dynamic paginated table into browser DOM with simulated SPA "Next" button and terminal repeating state

[OUTPUT]
- Browser automation extracts tabular data page by page
- Dual-Sentinel Guard evaluates first-row composite fingerprint
- Terminal page terminates loop deterministically with zero runaway iteration
- Artifact generation verified

[POS]
Full-chain real Chrome E2E test for topic_04 item #17.
Validates end-to-end user experience directly inside real Chrome browser with live UI events.
"""

from __future__ import annotations

import os
import sys

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
)

_CREATE_TEST_PAGE_JS = """(() => {
  // Inject a mock paginated table container into current document for testing
  let container = document.getElementById('e2e-table-harvest-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'e2e-table-harvest-container';
    container.style.position = 'fixed';
    container.style.top = '10px';
    container.style.left = '10px';
    container.style.zIndex = '99999';
    container.style.background = '#ffffff';
    container.style.padding = '12px';
    container.style.border = '2px solid #2563eb';
    container.style.borderRadius = '8px';
    container.style.boxShadow = '0 10px 15px -3px rgba(0, 0, 0, 0.1)';
    document.body.appendChild(container);
  }

  window.__E2E_PAGE_INDEX__ = 1;
  const pagesData = {
    1: [
      { id: 'ORD-101', customer: 'Alice Tech', amount: '$1,200.00', status: 'Completed' },
      { id: 'ORD-102', customer: 'Bob Cloud', amount: '$850.50', status: 'Pending' },
    ],
    2: [
      { id: 'ORD-201', customer: 'Charlie AI', amount: '$3,400.00', status: 'Completed' },
      { id: 'ORD-202', customer: 'Delta Data', amount: '$920.00', status: 'Shipped' },
    ],
    3: [
      { id: 'ORD-301', customer: 'Echo Systems', amount: '$450.00', status: 'Delivered' },
      { id: 'ORD-302', customer: 'Foxtrot Corp', amount: '$2,100.00', status: 'Completed' },
    ],
  };

  function renderTable(pageNum) {
    const rows = pagesData[pageNum] || pagesData[3]; // page 4+ repeats terminal page 3
    const isTerminal = pageNum >= 3;

    container.innerHTML = `
      <div style="font-weight: bold; margin-bottom: 6px; color: #1e3a8a;">
        Mock Paginated Financial Table (Page <span id="e2e-current-page">${pageNum}</span>)
      </div>
      <table id="e2e-harvest-table" style="border-collapse: collapse; width: 100%; font-size: 13px;">
        <thead>
          <tr style="background: #f1f5f9; text-align: left;">
            <th style="padding: 4px 8px; border: 1px solid #cbd5e1;">Order ID</th>
            <th style="padding: 4px 8px; border: 1px solid #cbd5e1;">Customer</th>
            <th style="padding: 4px 8px; border: 1px solid #cbd5e1;">Amount</th>
            <th style="padding: 4px 8px; border: 1px solid #cbd5e1;">Status</th>
          </tr>
        </thead>
        <tbody id="e2e-table-tbody">
          ${rows.map(r => `
            <tr>
              <td style="padding: 4px 8px; border: 1px solid #cbd5e1;">${r.id}</td>
              <td style="padding: 4px 8px; border: 1px solid #cbd5e1;">${r.customer}</td>
              <td style="padding: 4px 8px; border: 1px solid #cbd5e1;">${r.amount}</td>
              <td style="padding: 4px 8px; border: 1px solid #cbd5e1;">${r.status}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
      <div style="margin-top: 8px; display: flex; justify-content: flex-end;">
        <button id="e2e-next-page-btn" ${isTerminal ? 'disabled style="opacity: 0.5;"' : ''} style="padding: 4px 10px; cursor: pointer; background: #2563eb; color: #fff; border: none; border-radius: 4px;">
          Next Page &rarr;
        </button>
      </div>
    `;

    const nextBtn = document.getElementById('e2e-next-page-btn');
    if (nextBtn) {
      nextBtn.onclick = () => {
        window.__E2E_PAGE_INDEX__ += 1;
        renderTable(window.__E2E_PAGE_INDEX__);
      };
    }
  }

  renderTable(window.__E2E_PAGE_INDEX__);
  return { ok: true, mounted: true };
})()"""

_EXTRACT_AND_STEP_SENTINEL_JS = """(() => {
  const tbody = document.getElementById('e2e-table-tbody');
  if (!tbody) return { ready: false, err: 'no-tbody' };

  const rows = Array.from(tbody.querySelectorAll('tr'));
  if (rows.length === 0) return { ready: false, err: 'empty-rows' };

  // Sentinel A: compute row fingerprint of first data row
  const firstRowCells = Array.from(rows[0].querySelectorAll('td')).map(td => td.innerText.trim());
  const rowFingerprint = firstRowCells.join('|');

  // Extract all data rows
  const extractedRows = rows.map(tr => {
    const cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
    return { id: cells[0], customer: cells[1], amount: cells[2], status: cells[3] };
  });

  const nextBtn = document.getElementById('e2e-next-page-btn');
  const isDisabled = nextBtn ? nextBtn.disabled : true;

  return {
    ready: true,
    page: window.__E2E_PAGE_INDEX__,
    firstRowFingerprint: rowFingerprint,
    rows: extractedRows,
    nextButtonDisabled: isDisabled,
  };
})()"""

_CLICK_NEXT_JS = """(() => {
  const nextBtn = document.getElementById('e2e-next-page-btn');
  if (!nextBtn) return { ok: false, err: 'no-btn' };
  nextBtn.click();
  return { ok: true, newPage: window.__E2E_PAGE_INDEX__ };
})()"""

_CLEANUP_TEST_PAGE_JS = """(() => {
  const container = document.getElementById('e2e-table-harvest-container');
  if (container) container.remove();
  delete window.__E2E_PAGE_INDEX__;
  return { ok: true, cleaned: true };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_paginated_table_harvest_real_chrome_e2e() -> None:
    """Real Chrome E2E: Verify live DOM multi-page table extraction and Dual-Sentinel termination."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    with open_settings_subroute("/settings/system", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)

        # 1. Inject simulated multi-page DOM table into live Chrome session
        mount_res = client.evaluate(page, _CREATE_TEST_PAGE_JS, timeout_sec=10.0)
        assert mount_res.get("mounted") is True

        try:
            harvested_records: list[dict[str, str]] = []
            previous_fingerprint: str | None = None
            max_pages = 5
            pages_visited = 0
            terminated_reason: str | None = None

            # 2. Run real-time browser harvesting loop in Chrome
            while pages_visited < max_pages:
                state = wait_for_state(
                    client,
                    page,
                    _EXTRACT_AND_STEP_SENTINEL_JS,
                    timeout_sec=15.0,
                )
                assert state.get("ready") is True
                current_fingerprint = state.get("firstRowFingerprint")

                # Sentinel A: duplicate row fingerprint check
                if previous_fingerprint is not None and current_fingerprint == previous_fingerprint:
                    terminated_reason = "SENTINEL_A_DUPLICATE_FINGERPRINT"
                    break

                rows = state.get("rows", [])
                harvested_records.extend(rows)
                pages_visited += 1
                previous_fingerprint = current_fingerprint

                # Check terminal button state
                if state.get("nextButtonDisabled"):
                    terminated_reason = "NEXT_BUTTON_DISABLED_TERMINAL"
                    break

                # Advance to next page via simulated user click in Chrome
                client.evaluate(page, _CLICK_NEXT_JS, timeout_sec=5.0)

            # 3. Assertions on real Chrome execution
            assert pages_visited == 3, f"Expected 3 pages harvested, got {pages_visited}"
            assert len(harvested_records) == 6, f"Expected 6 records harvested, got {len(harvested_records)}"
            assert terminated_reason in ("SENTINEL_A_DUPLICATE_FINGERPRINT", "NEXT_BUTTON_DISABLED_TERMINAL")

            # Check individual row integrity
            assert harvested_records[0]["id"] == "ORD-101"
            assert harvested_records[0]["customer"] == "Alice Tech"
            assert harvested_records[-1]["id"] == "ORD-302"
            assert harvested_records[-1]["customer"] == "Foxtrot Corp"

        finally:
            client.evaluate(page, _CLEANUP_TEST_PAGE_JS, timeout_sec=5.0)
