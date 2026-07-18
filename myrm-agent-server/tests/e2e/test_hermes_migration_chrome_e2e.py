"""Real Chrome MCP E2E for Hermes migration wizard → builtin-economy dry-run.

Prerequisites:
  ./myrm ready --chrome
  Local Hermes source discoverable at ~/.hermes (or other path returned by discovery API)

Covers:
  - Scan step discovers Hermes source
  - User clicks preview (real UI flow, not deep-link race)
  - fetch hook captures POST /memory/import/dry-run body
  - UI shows hermesEconomyHint (zh/en)
  - Body contains migration.clone_from_agent_id=builtin-economy
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import get_e2e_api_url, get_e2e_ui_url  # noqa: E402
from chrome_mcp_client import ChromeMcpClient  # noqa: E402

_MIGRATION_SCAN_URL = f"{get_e2e_ui_url()}/settings/memory?sub=migration"

_FETCH_HOOK_JS = """(() => {
  window.__MYRM_DRY_RUN_CAPTURE__ = [];
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    try {
      const input = args[0];
      const url = typeof input === 'string' ? input : input?.url || '';
      if (url.includes('/memory/import/dry-run')) {
        const init = args[1];
        const rawBody = init && typeof init === 'object' ? init.body : null;
        if (typeof rawBody === 'string' && rawBody.trim()) {
          window.__MYRM_DRY_RUN_CAPTURE__.push({
            url,
            body: JSON.parse(rawBody),
          });
        }
      }
    } catch {
      // ignore capture failures — assertion will fail on empty capture
    }
    return response;
  };
  return { hooked: true };
})()"""

_SCAN_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasLayout = !!document.querySelector('[data-testid="app-layout"]');
  const hasHermesCard = /Hermes/i.test(text)
    && (/预览导入|Preview import/i.test(text));
  return {
    ready: hasLayout && hasHermesCard,
    url: location.href,
  };
})()"""

_CLICK_HERMES_PREVIEW_JS = """(() => {
  const cards = Array.from(document.querySelectorAll('div.rounded-xl.border'));
  for (const card of cards) {
    const text = card.innerText || '';
    if (!/Hermes/i.test(text)) continue;
    const button = card.querySelector('button');
    if (!button || button.disabled) continue;
    button.click();
    return { clicked: true, label: text.split('\\n')[0] || 'Hermes' };
  }
  return { clicked: false };
})()"""

_FINAL_ASSERT_JS = """(() => {
  const text = document.body?.innerText || '';
  const capture = window.__MYRM_DRY_RUN_CAPTURE__ || [];
  const first = capture[0];
  const body = first && typeof first === 'object' ? first.body : null;
  const migration = body && typeof body === 'object' ? body.migration : null;
  return {
    captureLen: capture.length,
    hasHint: /Economy 智能体预设|Economy agent preset/i.test(text),
    cloneFromAgentId:
      migration && typeof migration === 'object'
        ? migration.clone_from_agent_id
        : null,
    source: body && typeof body === 'object' ? body.source : null,
  };
})()"""


def _discover_has_hermes() -> bool:
    url = f"{get_e2e_api_url()}/api/v1/migration/discover"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:  # noqa: S310 - loopback
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False
    sources = payload.get("sources")
    if not isinstance(sources, list):
        return False
    return any(isinstance(item, dict) and item.get("competitor") == "hermes" for item in sources)


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_hermes_migration_wizard_dry_run_uses_builtin_economy() -> None:
    if not _discover_has_hermes():
        pytest.skip("No Hermes migration source discovered on this machine")

    with ChromeMcpClient() as client:
        page = client.new_page(_MIGRATION_SCAN_URL, timeout_ms=90_000)

        scan_deadline = time.monotonic() + 90.0
        while time.monotonic() < scan_deadline:
            raw = client.evaluate(page, _SCAN_READY_JS, timeout_sec=20.0)
            state = raw if isinstance(raw, dict) else {"value": raw}
            if state.get("ready"):
                break
            time.sleep(0.5)
        else:
            raise AssertionError(f"Hermes scan step did not become ready: {state!r}")

        client.evaluate(page, _FETCH_HOOK_JS, timeout_sec=10.0)
        clicked_raw = client.evaluate(page, _CLICK_HERMES_PREVIEW_JS, timeout_sec=10.0)
        clicked = clicked_raw if isinstance(clicked_raw, dict) else {}
        assert clicked.get("clicked") is True, f"Hermes preview button not clicked: {clicked!r}"

        deadline = time.monotonic() + 120.0
        final: dict[str, object] = {}
        while time.monotonic() < deadline:
            raw = client.evaluate(page, _FINAL_ASSERT_JS, timeout_sec=20.0)
            final = raw if isinstance(raw, dict) else {"value": raw}
            capture_len = final.get("captureLen") or 0
            if (
                isinstance(capture_len, int)
                and capture_len > 0
                and final.get("hasHint") is True
                and final.get("cloneFromAgentId") == "builtin-economy"
            ):
                break
            time.sleep(0.5)
        else:
            raise AssertionError(f"Hermes dry-run assertions not satisfied: {final!r}")

        assert final.get("cloneFromAgentId") == "builtin-economy"
        assert final.get("hasHint") is True
