"""Chrome READ E2E: Settings > System storage card (data directory + usage).

Verifies the StorageCard section renders in a real browser: current data-dir
path label plus either the Tauri Change button or the web/cloud hint, and the
disk-usage readout. Covers the DataRootPathMigrationWizard front-end chain at
the page-contract level (migration invoke itself needs the Tauri runtime).
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_SETTINGS_SHELL_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  return {
    ready:
      location.pathname.startsWith('/settings') &&
      bodyText.length > 20 &&
      !!document.querySelector('[data-testid="settings-layout"]'),
    pathname: location.pathname,
    bodyLength: bodyText.length,
  };
})()"""

_STORAGE_CARD_JS = """(() => {
  const labels = Array.from(document.querySelectorAll('label'));
  const label = labels.find((el) => /Current Data Directory|当前数据目录|目前資料目錄|現在のデータディレクトリ|현재 데이터 디렉터리|Aktuelles Datenverzeichnis/.test(el.textContent || ''));
  if (!label) {
    return { ready: false, reason: 'no-path-label', bodyLength: (document.body?.innerText || '').length };
  }
  const card = label.closest('section') || label.parentElement;
  const cardText = (card && card.textContent) || '';
  // Path value line: the mono truncated <p> next to the label (E2E runtimes use isolated dirs, so match path-likeness, not '.myrm').
  const hasPathValue = /\\/|~|:\\\\/.test(cardText);
  const hasUsage = /\\bGB\\b|\\bMB\\b|\\bKB\\b|\\bB\\b|已用|已使用|使用量|剩余|可用/.test(cardText);
  const buttons = card ? Array.from(card.querySelectorAll('button')) : [];
  const hasChangeButton = buttons.some((b) => /^(Change|更改|變更)$/.test((b.textContent || '').trim()));
  const hasHint = /MYRM_DATA_DIR|Persistent Volume|持久化|沙箱|沙盒|WebUI/.test(cardText);
  return {
    ready: hasPathValue && hasUsage && (hasChangeButton || hasHint),
    hasPathValue,
    hasUsage,
    hasChangeButton,
    hasHint,
    cardSnippet: cardText.slice(0, 400),
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
def test_chrome_ui_storage_card_renders() -> None:
    """Storage card must render path + usage + change/hint in real browser."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    warm_ui_route("/settings")
    warm_ui_route(
        "/settings/system",
        timeout_sec=_warm_ui_parallel_wait_sec(180.0),
    )
    with open_settings_subroute(
        "/settings/system",
        timeout_ms=120_000,
    ) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page)

        shell = wait_for_state(
            client,
            page,
            _SETTINGS_SHELL_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert shell.get("ready") is True, json.dumps(shell, indent=2, ensure_ascii=False)

        card = wait_for_state(
            client,
            page,
            _STORAGE_CARD_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert card.get("ready") is True, json.dumps(card, indent=2, ensure_ascii=False)
