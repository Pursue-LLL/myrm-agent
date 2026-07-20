"""Real Chrome MCP E2E: wiki citation reload + settings wiki agent scope deeplink."""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
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


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_wiki_citation_button_survives_reload() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_wiki_citation_fixture(api_url)
    chat_id = str(seeded["chat_id"])

    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        first_state = wait_for_state(
            client,
            page,
            _CITATION_BUTTON_STATE,
            timeout_sec=90.0,
        )
        assert first_state.get("ready") is True
        assert str(first_state.get("label") or "")

        client.reload(page, timeout_ms=60_000)
        reloaded_state = wait_for_state(
            client,
            page,
            _CITATION_BUTTON_STATE,
            timeout_sec=90.0,
        )
        assert reloaded_state.get("ready") is True


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_settings_wiki_agent_scope_deeplink() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_wiki_citation_fixture(api_url)
    agent_id = str(seeded["agent_id"])
    wiki_settings_path = str(seeded["wiki_settings_path"])

    warm_ui_route(wiki_settings_path)
    with open_mcp_page(f"{ui_url}{wiki_settings_path}", timeout_ms=120_000) as (client, page):
        scope_state = wait_for_state(
            client,
            page,
            _wiki_agent_scope_state(agent_id),
            timeout_sec=90.0,
        )
        assert scope_state.get("ready") is True
        assert "/settings/wiki" in str(scope_state.get("pathname") or "")
        assert "agentId=" in str(scope_state.get("search") or "")
