"""Chrome READ E2E: Memory evolution history timeline in MemoryDetailSheet on real WebUI.

Business flow (Lane-B):
1. Seed a semantic memory with merge audit data (merge_count / merge_history) via the
   memory API on the private-epoch backend.
2. Open the real memory management page in Chrome (settings -> knowledge -> memory).
3. Open the seeded memory detail sheet and assert the evolution timeline renders
   audit entries and the merge count badge.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable

import pytest

from tests.support.chrome_mcp_e2e import (
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))


def _seed_evolving_memory(api_url: str) -> dict[str, object]:
    """Seed evolving memory via the local test fixture (bootstraps embedding + memory)."""
    item = http_json("POST", f"{api_url}/api/v1/memory/test/seed-evolution-fixture")
    assert item.get("id"), f"seed evolution fixture failed: {item}"
    return item


_MEMORY_SECTION_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const hasTabs = /待处理|Pending|全部|All/.test(text);
  return { ready: hasTabs, hasTabs, text: text.slice(0, 300) };
})()"""

_CLICK_ALL_TAB_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => /^\\s*(全部|All)\\s*$/.test(el.textContent || ''),
  );
  if (!btn) return { ready: false, clicked: false };
  btn.click();
  return { ready: true, clicked: true };
})()"""

_SEED_CARD_READY_JS = """(() => {
  const text = document.body?.textContent || '';
  const hasSeed = text.includes('E2E evolution seed');
  return { ready: hasSeed, hasSeed, text: text.slice(0, 400) };
})()"""

_DETAIL_SHEET_OPEN_JS = """(() => {
  // 1) 优先通过 content-btn 查找
  const contentBtns = Array.from(document.querySelectorAll('[data-testid="memory-card-content-btn"]'));
  const targetBtn = contentBtns.find((el) => (el.textContent || '').includes('E2E evolution seed'));
  if (targetBtn) {
    targetBtn.click();
    return { ok: true, method: 'testid_content_btn', tag: targetBtn.tagName };
  }
  // 2) 优先通过 memory-card 容器查找
  const cards = Array.from(document.querySelectorAll('[data-testid="memory-card"]'));
  const targetCard = cards.find((el) => (el.textContent || '').includes('E2E evolution seed'));
  if (targetCard) {
    targetCard.click();
    return { ok: true, method: 'testid_card', tag: targetCard.tagName };
  }
  // 3) 回退通用匹配
  const all = [...document.querySelectorAll('div, button')];
  const candidates = all.filter((el) => (el.textContent || '').includes('E2E evolution seed'));
  if (!candidates.length) {
    return { ok: false, err: 'seed card not found', sampleText: (document.body.innerText || '').slice(0, 300) };
  }
  let card = candidates[candidates.length - 1];
  for (const el of candidates) {
    if ((el.textContent || '').trim() === 'E2E evolution seed - user prefers dark mode (v3)') {
      card = el;
      break;
    }
  }
  card.click();
  return { ok: true, method: 'fallback_leaf', tag: card.tagName };
})()"""

_SHEET_PROBE_JS = """(() => {
  const sheetEl = document.querySelector('[data-testid="memory-detail-sheet"], [role="dialog"]');
  const historyEl = document.querySelector('[data-testid="evolution-history"]');
  const countEl = document.querySelector('[data-testid="merge-count"]');
  const actionEl = document.querySelector('[data-testid="merge-action"]');
  const text = document.body.innerText || '';

  const sheetOpen = Boolean(sheetEl || historyEl || /Evolution History|演变历史|演變歷史|変遷履歴|변천 이력|Entwicklungshistorie/.test(text));
  const hasMergeBadge = Boolean(countEl || /Merged \\d+ times|已合并 \\d+ 次|已合併 \\d+ 次|\\d+ 回マージ済み|\\d+회 병合됨|\\d+x zusammengeführt/.test(text));
  const hasMergeAction = Boolean(actionEl || /Merged|Replaced|Supplemented|合并|替换|补充|合併|替換|マージ|置換|補足|병합|대체|보완|Zusammengeführt|Ersetzt|Ergänzt/.test(text));

  return {
    ready: sheetOpen && hasMergeBadge && hasMergeAction,
    sheetOpen,
    hasMergeBadge,
    hasMergeAction,
    sample: text.slice(0, 200),
  };
})()"""

_SHEET_CLOSE_JS = """(() => {
  // Radix Sheet: 右上角关闭按钮（aria-label）优先；回退 Escape 由 harness 处理
  const btn = document.querySelector('[data-state="open"] [data-radix-collection-item], [data-radix-sheet-close], button[aria-label*="Close"], button[aria-label*="关闭"], button[aria-label*="關閉"]');
  if (!btn) return { ok: false, err: 'close btn not found' };
  btn.click();
  return { ok: true };
})()"""

_CORRECTED_SHEET_OPEN_JS = """(() => {
  const contentBtns = Array.from(document.querySelectorAll('[data-testid="memory-card-content-btn"]'));
  const targetBtn = contentBtns.find((el) => (el.textContent || '').includes('user prefers dark mode (corrected v1)'));
  if (targetBtn) {
    targetBtn.click();
    return { ok: true, method: 'testid_content_btn', tag: targetBtn.tagName };
  }
  const cards = Array.from(document.querySelectorAll('[data-testid="memory-card"]'));
  const targetCard = cards.find((el) => (el.textContent || '').includes('user prefers dark mode (corrected v1)'));
  if (targetCard) {
    targetCard.click();
    return { ok: true, method: 'testid_card', tag: targetCard.tagName };
  }
  const all = [...document.querySelectorAll('div, button')];
  const candidates = all.filter((el) => (el.textContent || '').includes('user prefers dark mode (corrected v1)'));
  if (!candidates.length) {
    return { ok: false, err: 'corrected card not found', sampleText: (document.body.innerText || '').slice(0, 300) };
  }
  let card = candidates[candidates.length - 1];
  for (const el of candidates) {
    if ((el.textContent || '').trim() === 'user prefers dark mode (corrected v1)') {
      card = el;
      break;
    }
  }
  card.click();
  return { ok: true, method: 'fallback_leaf', tag: card.tagName };
})()"""

_CORRECTION_PROBE_JS = """(() => {
  const chainEl = document.querySelector('[data-testid="correction-chain"]');
  const text = document.body.innerText || '';
  const hasCorrectionBadge = Boolean(chainEl || /Corrects|纠正|糾正|修正|수정|Korrigiert/.test(text));
  const hasSupersededContent = Boolean(chainEl || /corrected v1/.test(text));
  return {
    ready: hasCorrectionBadge,
    hasCorrectionBadge,
    hasSupersededContent,
    sample: text.slice(0, 200),
  };
})()"""

_RETRY_MARKERS: tuple[str, ...] = (
    "CDP request timeout",
    "Runtime.evaluate",
    "Chrome MCP",
    "connection reset",
    "Page not on localhost",
    "timed out",
    "Connection refused",
    "E2E_MUX_DAEMONS",
    "muxDaemons",
    "Browser state did not become ready",
)


def _run_with_transport_retry(
    runner: Callable[[str, str], None],
    api_url: str,
    ui_url: str,
    *,
    max_attempts: int = 3,
) -> None:
    """Retry transport-level failures only; assertion failures fail fast."""
    last_error: BaseException | None = None
    for _attempt in range(1, max_attempts + 1):
        try:
            _require_e2e_cdp_ready(budget_sec=45.0)
            runner(api_url, ui_url)
            return
        except BaseException as exc:
            if "E2E_USER_CLOSED_TAB" in str(exc):
                raise
            if not any(marker in str(exc) for marker in _RETRY_MARKERS):
                raise
            last_error = exc
            time.sleep(3.0)
    raise AssertionError(f"E2E transport retries exhausted: {last_error}")


def _run_evolution_assertions(api_url: str, ui_url: str) -> None:
    del ui_url  # open_settings_subroute 内部用 get_e2e_ui_url()
    seeded = _seed_evolving_memory(api_url)
    assert seeded.get("status") == "seeded", json.dumps(seeded, ensure_ascii=False)

    warm_ui_route("/settings/memory")

    # SSOT 基建：open /settings shell → 子路由 → settings-layout 就绪等待
    with open_settings_subroute("/settings/memory", timeout_ms=120_000) as (
        client,
        page,
    ):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(
            client, page, recover_url=f"{get_e2e_ui_url().rstrip('/')}/settings"
        )

        # 1) 等待记忆管理 section 渲染（tab 切换器出现 = 列表区已挂载）
        wait_for_state(
            client,
            page,
            _MEMORY_SECTION_READY_JS,
            timeout_sec=90.0,
        )
        # 2) 默认 pending tab；点击「全部」tab 切到全量列表
        switched = wait_for_state(client, page, _CLICK_ALL_TAB_JS, timeout_sec=45.0)
        assert switched.get("clicked") is True, json.dumps(switched, ensure_ascii=False)

        # 3) 等 seed 卡片出现在「全部」列表
        wait_for_state(client, page, _SEED_CARD_READY_JS, timeout_sec=90.0)

        # 4) 打开详情 Sheet
        opened = client.evaluate(page, _DETAIL_SHEET_OPEN_JS, timeout_sec=30.0)
        assert opened.get("ok") is True, json.dumps(opened, ensure_ascii=False)
        time.sleep(1.0)

        # 5) 断言演变历史渲染
        sheet = wait_for_state(client, page, _SHEET_PROBE_JS, timeout_sec=45.0)
        assert sheet.get("hasMergeBadge") is True, json.dumps(sheet, ensure_ascii=False)
        assert sheet.get("hasMergeAction") is True, json.dumps(
            sheet, ensure_ascii=False
        )

        # 6) Close the sheet, open the corrected card, assert the correction-chain entry renders
        client.evaluate(page, _SHEET_CLOSE_JS, timeout_sec=15.0)
        time.sleep(1.0)
        opened2 = client.evaluate(page, _CORRECTED_SHEET_OPEN_JS, timeout_sec=30.0)
        assert opened2.get("ok") is True, json.dumps(opened2, ensure_ascii=False)
        correction = wait_for_state(
            client, page, _CORRECTION_PROBE_JS, timeout_sec=45.0
        )
        assert correction.get("hasCorrectionBadge") is True, json.dumps(
            correction, ensure_ascii=False
        )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.e2e_search_policy("empty")
def test_chrome_ui_memory_evolution_history_sheet() -> None:
    """Seeded memory with merge audit renders evolution timeline in detail sheet."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_with_transport_retry(_run_evolution_assertions, api_url, ui_url)
