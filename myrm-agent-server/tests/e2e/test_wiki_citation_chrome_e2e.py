"""Real Chrome MCP E2E: wiki citation reload + settings wiki agent scope deeplink."""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    open_settings_subroute,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_CITATION_BUTTON_STATE = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const hit = buttons.find((button) => {
    const label = (button.textContent || '').trim();
    const aria = button.getAttribute('aria-label') || '';
    return /依据\\s*\\d+|Evidence\\s*\\d+/i.test(label) ||
      /sources and memories|条依据/i.test(aria);
  });
  return {
    ready: !!hit,
    label: hit?.textContent?.trim() || hit?.getAttribute('aria-label') || '',
  };
})()"""


_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""


_BRIDGE_ATTACH_READY_JS = """(() => ({
  ready: typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function',
}))()"""


def _attach_chat_probe(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {{
    return {{ ok: false, err: 'no-bridge' }};
  }}
  await bridge.attachToChat({chat_id_json});
  const snap = bridge.turnSnapshot?.() ?? {{}};
  return {{
    ok: snap.chatId === {chat_id_json},
    snap,
  }};
}})()"""


def _chat_shell_ready_js(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(() => {{
  const state = window.__MYRM_E2E_CHAT__?.getChatShellState?.() ?? {{}};
  return {{
    ready:
      state.chatId === {chat_id_json}
      && state.isMessagesLoaded === true
      && state.notFound !== true
      && state.loadError !== true,
    state,
  }};
}})()"""


_CITATIONS_IN_STORE_JS = """(() => {

  const store = window.__myrmChatStore?.getState?.();
  if (!store) {
    return { ready: false, reason: 'no-store' };
  }
  const assistant = (store.messages ?? []).filter((m) => m.role === 'assistant');
  const last = assistant[assistant.length - 1];
  const citeIds = last?.citedMemoryIds?.length ?? 0;
  const citeRefs = last?.citedMemoryRefs?.length ?? 0;
  return {
    ready: citeIds + citeRefs > 0 && !store.loading,
    citeIds,
    citeRefs,
    msgCount: store.messages?.length ?? 0,
    loading: store.loading,
    notFound: store.notFound,
    loadError: store.loadError,
  };
})()"""


def _wiki_agent_scope_state(agent_id: str) -> str:
    return f"""(() => {{
  const layout = document.querySelector('[data-testid="app-layout"]');
  const onWiki = location.pathname.endsWith('/settings/wiki');
  const params = new URLSearchParams(location.search);
  const scopedAgentId = params.get('agentId');
  return {{
    ready: !!layout && onWiki && scopedAgentId === {json.dumps(agent_id)},
    pathname: location.pathname,
    search: location.search,
  }};
}})()"""


def _seed_wiki_citation_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-citation-fixture")
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    agent_id = str(seeded.get("agent_id") or "")
    agent_name = str(seeded.get("agent_name") or "")
    wiki_settings_path = str(seeded.get("wiki_settings_path") or "")
    citation_count = seeded.get("citation_count")
    assert chat_id.startswith("e2ewiki")
    assert len(agent_id) >= 8
    assert agent_name
    assert wiki_settings_path.startswith("/settings/wiki?agentId=")
    assert citation_count == 10
    return seeded


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_wiki_citation_button_survives_reload() -> None:

    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_wiki_citation_fixture(api_url)
    chat_id = str(seeded["chat_id"])

    warm_ui_route(f"/{chat_id}")
    chat_url = f"{ui_url}/{chat_id}"
    with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        ensure_desktop_viewport(client, page)
        wait_for_state(
            client,
            page,
            _BRIDGE_ATTACH_READY_JS,
            timeout_sec=120.0,
            page_url=chat_url,
        )
        client.evaluate(
            page,
            _attach_chat_probe(chat_id),
            timeout_sec=90.0,
        )
        shell = wait_for_state(
            client,
            page,
            _chat_shell_ready_js(chat_id),
            timeout_sec=120.0,
            page_url=chat_url,
        )
        assert shell.get("ready") is True, shell
        citations = wait_for_state(
            client,
            page,
            _CITATIONS_IN_STORE_JS,
            timeout_sec=120.0,
            page_url=chat_url,
        )
        assert citations.get("ready") is True, citations

        first_state = wait_for_state(
            client,
            page,
            _CITATION_BUTTON_STATE,
            timeout_sec=60.0,
            page_url=chat_url,
        )
        assert first_state.get("ready") is True
        assert str(first_state.get("label") or "")

        reload_mcp_page(client, page, timeout_ms=60_000, target_url=chat_url)
        dismiss_blocking_modals(client, page, recover_url=chat_url)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        wait_for_state(
            client,
            page,
            _BRIDGE_ATTACH_READY_JS,
            timeout_sec=120.0,
            page_url=chat_url,
        )
        client.evaluate(
            page,
            _attach_chat_probe(chat_id),
            timeout_sec=90.0,
        )
        wait_for_state(
            client,
            page,
            _chat_shell_ready_js(chat_id),
            timeout_sec=120.0,
            page_url=chat_url,
        )
        reloaded_state = wait_for_state(
            client,
            page,
            _CITATION_BUTTON_STATE,
            timeout_sec=90.0,
            page_url=chat_url,
        )
        assert reloaded_state.get("ready") is True



@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_settings_wiki_agent_scope_deeplink() -> None:

    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_wiki_citation_fixture(api_url)
    agent_id = str(seeded["agent_id"])
    wiki_settings_path = str(seeded["wiki_settings_path"])

    warm_ui_route(wiki_settings_path)
    with open_settings_subroute(wiki_settings_path, timeout_ms=120_000) as (
        client,
        page,
    ):
        scope_state = wait_for_state(
            client,
            page,
            _wiki_agent_scope_state(agent_id),
            timeout_sec=90.0,
        )
        assert scope_state.get("ready") is True
        assert "/settings/wiki" in str(scope_state.get("pathname") or "")
        assert "agentId=" in str(scope_state.get("search") or "")
