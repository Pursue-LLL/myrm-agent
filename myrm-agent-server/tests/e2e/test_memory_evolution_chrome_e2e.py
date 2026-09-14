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

import pytest
import os
import sys
import time
from collections.abc import Callable

from tests.support.chrome_mcp_e2e import (
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
  } catch (_) {}
  return 'ok';
})()"""


def _seed_evolving_memory(api_url: str) -> dict[str, object]:
    """Seed one semantic memory carrying merge audit fields via the real memory API."""
    payload = {
        "memory_type": "semantic",
        "content": "E2E evolution seed - user prefers dark mode (v3)",
        "importance": 0.8,
        "confidence": 0.9,
        "metadata": {
            "merge_count": 2,
            "merge_history": "09-12 10:00|MERGE|prefers dark mode\n09-13 18:30|REPLACE|moved dark mode preference to global scope",
        },
        "tags": ["e2e-evolution"],
    }
    item = http_json("POST", f"{api_url}/api/v1/memory/", payload=payload)
    assert item.get("id"), f"seed memory create failed: {item}"
    return item


_EVO_PAGE_PROBE_JS = """(() => {
  const text = document.body.innerText;
  return {
    ready: text.length > 100,
    cardCount: document.querySelectorAll('[class*="memory-card"], [class*="MemoryCard"]').length,
    hasEvolutionBadge: /Merged \\d+ times|已合并 \\d+ 次/.test(text),
  };
})()"""

_DETAIL_SHEET_OPEN_JS = """(target) => {
  const cards = [...document.querySelectorAll('div, button')]
    .filter((el) => (el.textContent || '').includes('E2E evolution seed'));
  const card = cards[cards.length - 1];
  if (!card) {
    return { ok: false, err: 'seed card not found' };
  }
  card.click();
  return { ok: true };
}"""

_SHEET_PROBE_JS = """(() => {
  const text = document.body.innerText;
  return {
    sheetOpen: /Evolution History|演变历史/.test(text),
    hasMergeBadge: /Merged \\d+ times|已合并 \\d+ 次/.test(text),
    hasMergeAction: /Merged|Replaced|Supplemented|合并|替换|补充/.test(text),
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
    _seed_evolving_memory(api_url)
    settings_url = f"{ui_url.rstrip('/')}/settings/knowledge"
    home_url = f"{ui_url.rstrip('/')}/"

    warm_ui_route("/settings/knowledge")
    warm_ui_route("/")

    with open_mcp_page(home_url, timeout_ms=120_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page, recover_url=home_url)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)

        client.navigate(page, settings_url)  # type: ignore[attr-defined]
        time.sleep(2.0)
        dismiss_blocking_modals(client, page, recover_url=settings_url)

        wait_for_state(
            client,
            page,
            _EVO_PAGE_PROBE_JS,
            timeout_sec=60.0,
            page_url=settings_url,
        )
        time.sleep(1.0)

        opened = client.evaluate(page, _DETAIL_SHEET_OPEN_JS, timeout_sec=30.0)
        assert opened.get("ok") is True, json.dumps(opened, ensure_ascii=False)
        time.sleep(1.5)

        sheet = client.evaluate(page, _SHEET_PROBE_JS, timeout_sec=30.0)
        assert sheet.get("hasEvolutionBadge") is True, json.dumps(sheet, ensure_ascii=False)
        assert sheet.get("hasMergeAction") is True, json.dumps(sheet, ensure_ascii=False)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
def test_chrome_ui_memory_evolution_history_sheet() -> None:
    """Seeded memory with merge audit renders evolution timeline in detail sheet."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_with_transport_retry(_run_evolution_assertions, api_url, ui_url)
