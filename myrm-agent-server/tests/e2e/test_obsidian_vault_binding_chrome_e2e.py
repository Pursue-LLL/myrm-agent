"""Real Chrome MCP E2E: Obsidian vault binding in Wiki settings.

The local vault path is the only way this product ingests notes, so the settings
card has to render it in local mode and must not resurrect the inbox write switch
that was removed because nothing consumed it.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_wiki_settings_mcp_page,
    wait_for_wiki_settings_shell,
    warm_ui_route,
)

_PROBE_JS = """(() => {
  const card = document.querySelector('[data-testid="wiki-obsidian-vault-binding"]');
  if (!card) {
    return { found: false, url: window.location.href, bodyHasWiki: (document.body.innerText || '').includes('Obsidian') };
  }
  const inputs = Array.from(card.querySelectorAll('input')).map(i => i.placeholder || i.type);
  const buttons = Array.from(card.querySelectorAll('button')).map(b => (b.textContent || '').trim()).filter(Boolean);
  const text = card.innerText || '';
  return {
    found: true,
    inputs,
    buttons,
    hasPathInput: inputs.length > 0,
    showsCloudHint: /browser|cloud|browser-based|浏览器|云端|云端环境/i.test(text),
    mentionsInboxWrite: /inbox|收件箱|allow.?inbox/i.test(text),
    text: text.slice(0, 400),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_obsidian_vault_binding_settings_chrome_e2e() -> None:
    """The vault path input renders in local mode and the inbox write switch stays gone."""
    _require_e2e_cdp_ready()
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    binding = http_json("GET", f"{api_url}/api/v1/wiki/vault/binding")
    assert isinstance(binding, dict), binding
    assert set(binding) == {
        "is_bound",
        "vault_path",
        "is_active",
        "last_sync_watermark",
        "updated_at",
    }, f"binding contract drifted: {sorted(binding)}"

    wiki_page_url = f"{ui_url.rstrip('/')}/settings/wiki"
    warm_ui_route("/settings")
    warm_ui_route("/settings/wiki")

    with open_wiki_settings_mcp_page(wiki_page_url, timeout_ms=120_000, request_timeout_sec=180.0) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page, recover_url=wiki_page_url)
        wait_for_wiki_settings_shell(client, page, page_url=wiki_page_url)

        state = client.evaluate(page, _PROBE_JS, timeout_sec=30.0)
        assert state.get("found"), state
        assert state["hasPathInput"], state
        assert not state["showsCloudHint"], f"local mode must bind a path directly: {state['text']}"
        assert not state["mentionsInboxWrite"], f"removed inbox write control is still rendered: {state['text']}"
