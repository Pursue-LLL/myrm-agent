"""Real Chrome + live API integration test for microsoft-todo Chinese discoverability.

Covers the full user-facing chain for the #5 Microsoft To Do connector:
1. Live catalog API returns the microsoft-todo entry (official Chinese name + tags).
2. Chinese keyword search in the Service Directory UI surfaces the card.
3. Connecting opens the dialog with the zero-config device-code guidance
   (auth=none helpText + helpUrl learn-more link).
"""

from __future__ import annotations

import time
import urllib.parse

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)

_ENTRY_TITLE_RE = r"Microsoft To Do|微软待办"


def _is_retryable_open_mcp_error(exc: RuntimeError) -> bool:
    message = str(exc)
    if "No McpPage found for the given page" in message:
        return True
    if "SHPOIB runtime rebind after reload failed" in message:
        return True
    if "pageId " in message and "not owned by this shim session" in message:
        return True
    if "Chrome MCP new_page failed: Error: Timed out after waiting 30000ms" in message:
        return True
    return False


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_microsoft_todo_chinese_discoverability_and_connect_guide() -> None:
    api_url = get_e2e_api_url()

    # 1) Live API: Chinese keyword search must hit microsoft-todo.
    for query in ("待办", "微软", "微软待办"):
        encoded = urllib.parse.quote(query)
        search = http_json("GET", f"{api_url}/api/v1/integrations/catalog?q={encoded}")
        assert isinstance(search, dict)
        payload = search.get("data")
        assert isinstance(payload, dict)
        ids = {e.get("id") for e in payload.get("entries", []) if isinstance(e, dict)}
        assert "microsoft-todo" in ids, f"search '{query}' must return microsoft-todo, got {ids}"

    # 2) Live API: entry exposes zero-config guidance fields consumed by the UI.
    detail = http_json("GET", f"{api_url}/api/v1/integrations/catalog/microsoft-todo")
    assert isinstance(detail, dict)
    entry = detail.get("data")
    assert isinstance(entry, dict)
    assert entry.get("authType") == "none"
    assert entry.get("nameZh") == "微软待办"
    assert "待办" in entry.get("tags", [])
    assert entry.get("helpText"), "auth=none entry must carry helpText for the connect dialog"
    assert entry.get("helpUrl") == "https://to-do.office.com"

    # 3) Real Chrome UI chain.
    warm_ui_route("/settings/integrationCatalog")
    last_open_error: RuntimeError | None = None
    for attempt in range(3):
        try:
            with open_settings_subroute("/settings/integrationCatalog", timeout_ms=90_000) as (client, page):
                # Type the Chinese keyword into the Service Directory search box.
                typed = client.evaluate(
                    page,
                    """(() => {
                      const inputs = Array.from(document.querySelectorAll('input'));
                      const search = inputs.find((el) => {
                        const ph = (el.getAttribute('placeholder') || '').toLowerCase();
                        return ph.includes('search') || ph.includes('搜索') || ph.includes('搜尋');
                      });
                      if (!search) return { ok: false, reason: 'search_input_missing' };
                      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                      setter.call(search, '待办');
                      search.dispatchEvent(new Event('input', { bubbles: true }));
                      return { ok: true };
                    })()""",
                    timeout_sec=8.0,
                )
                assert isinstance(typed, dict)
                assert typed.get("ok") is True, f"failed to type query: {typed}"

                # The microsoft-todo card must appear after the local filter.
                card = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const titles = Array.from(document.querySelectorAll('h4')).map((el) =>
                        el.textContent || ''
                      );
                      const found = titles.some((t) => /Microsoft To Do|微软待办/i.test(t));
                      return { ready: found, titles };
                    })()""",
                    timeout_sec=15.0,
                )
                assert isinstance(card, dict)
                assert card.get("ready") is True, f"microsoft-todo card missing: {card}"

                # Open the connect dialog from the card.
                open_dialog = client.evaluate(
                    page,
                    """(() => {
                      const titles = Array.from(document.querySelectorAll('h4'));
                      const title = titles.find((el) =>
                        /Microsoft To Do|微软待办/i.test(el.textContent || '')
                      );
                      if (!title) return { ok: false, reason: 'entry_missing' };
                      const cardEl = title.closest('div');
                      if (!cardEl) return { ok: false, reason: 'card_missing' };
                      const button = Array.from(cardEl.querySelectorAll('button')).find((el) =>
                        /Connect|连接|連線/i.test(el.textContent || '')
                      );
                      if (!button) return { ok: false, reason: 'card_connect_missing' };
                      button.click();
                      return { ok: true };
                    })()""",
                    timeout_sec=8.0,
                )
                assert isinstance(open_dialog, dict)
                assert open_dialog.get("ok") is True, f"failed to open dialog: {open_dialog}"

                # Dialog must surface zero-config device-code guidance + learn-more link.
                guide = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const dialogs = Array.from(document.querySelectorAll('[role="dialog"]'));
                      if (!dialogs.length) return { ready: false, reason: 'dialog_missing' };
                      const dialog = dialogs[dialogs.length - 1];
                      const text = dialog.textContent || '';
                      const links = Array.from(dialog.querySelectorAll('a')).map((a) => ({
                        href: a.getAttribute('href'),
                        text: a.textContent || '',
                      }));
                      return {
                        ready: true,
                        textSnippet: text.slice(0, 700),
                        links,
                        dialogCount: dialogs.length,
                        hasMicrosoftHint: /Microsoft account|Microsoft 账户|微软账户/i.test(text),
                        hasLearnMore: links.some((l) => (l.href || '').includes('to-do.office.com')),
                      };
                    })()""",
                    timeout_sec=15.0,
                )
                assert isinstance(guide, dict)
                assert guide.get("ready") is True, f"connect dialog missing: {guide}"
                assert guide.get("hasMicrosoftHint") is True, f"device-code hint missing: {guide}"
                assert guide.get("hasLearnMore") is True, f"learn-more link missing: {guide}"
            return
        except RuntimeError as exc:
            last_open_error = exc
            if not _is_retryable_open_mcp_error(exc) or attempt == 2:
                raise
            time.sleep(2.0)
    raise AssertionError(f"failed to open MCP page after retries: {last_open_error}")
