"""Real Chrome MCP E2E: wiki citation reload + settings wiki agent scope deeplink."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
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

_CHAT_SHELL_READY_JS = """(() => {
  const state = window.__MYRM_E2E_CHAT__?.getChatShellState?.() ?? {};
  return {
    ready:
      state.isMessagesLoaded === true
      && state.notFound !== true
      && state.loadError !== true,
    state,
  };
})()"""


def _bind_private_runtime_and_navigate(client, page, chat_url: str, api_url: str) -> None:
    """Seed window.name then navigate so e2e-runtime-bootstrap.js proxies API to SHPOIB."""
    dev_lib = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
    if str(dev_lib) not in sys.path:
        sys.path.insert(0, str(dev_lib))
    from cdp_chat_support import e2e_runtime_binding_source  # noqa: PLC0415

    source = e2e_runtime_binding_source()
    assert source, (
        "SHPOIB runtime binding source missing — "
        f"E2E_API_BASE={api_url!r}"
    )
    client.evaluate(
        page,
        f"(() => {{{source} return window.__MYRM_E2E_API_BASE__; }})()",
        timeout_sec=30.0,
    )
    client.navigate(page, chat_url, timeout_ms=90_000)


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


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD")
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
    with open_mcp_page("about:blank") as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        _bind_private_runtime_and_navigate(client, page, chat_url, api_url)
        wait_for_state(
            client,
            page,
            _BRIDGE_ATTACH_READY_JS,
            timeout_sec=120.0,
        )
        shell = wait_for_state(
            client,
            page,
            _CHAT_SHELL_READY_JS,
            timeout_sec=120.0,
        )
        assert shell.get("ready") is True, shell
        citations = wait_for_state(
            client,
            page,
            _CITATIONS_IN_STORE_JS,
            timeout_sec=120.0,
        )
        assert citations.get("ready") is True, citations

        first_state = wait_for_state(
            client,
            page,
            _CITATION_BUTTON_STATE,
            timeout_sec=60.0,
        )
        assert first_state.get("ready") is True
        assert str(first_state.get("label") or "")

        reload_mcp_page(client, page, timeout_ms=60_000, target_url=chat_url)
        _bind_private_runtime_and_navigate(client, page, chat_url, api_url)
        wait_for_state(
            client,
            page,
            _CHAT_SHELL_READY_JS,
            timeout_sec=120.0,
        )
        reloaded_state = wait_for_state(
            client,
            page,
            _CITATION_BUTTON_STATE,
            timeout_sec=90.0,
        )
        assert reloaded_state.get("ready") is True


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_settings_wiki_agent_scope_deeplink() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_wiki_citation_fixture(api_url)
    agent_id = str(seeded["agent_id"])
    wiki_settings_path = str(seeded["wiki_settings_path"])

    warm_ui_route(wiki_settings_path)
    with open_mcp_page(f"{ui_url}{wiki_settings_path}", timeout_ms=120_000) as (
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
