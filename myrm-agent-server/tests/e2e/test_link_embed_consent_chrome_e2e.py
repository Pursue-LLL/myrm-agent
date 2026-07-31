"""Real Chrome MCP E2E: link embed consent modes (ask / always / off)."""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    reload_mcp_page,
    wait_for_state,
)


def _seed_embed_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-embed-fixture")
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    youtube_url = str(seeded.get("youtube_url") or "")
    assert chat_id.startswith("e2eembed")
    assert "dQw4w9WgXcQ" in youtube_url
    return seeded


def _set_embed_mode_expression(mode: str) -> str:
    return f"""(() => {{
  const mode = {json.dumps(mode)};
  localStorage.setItem(
    'myrm-embed-consent',
    JSON.stringify({{ state: {{ embedMode: mode, allowedProviders: [] }}, version: 0 }}),
  );
  return {{ ok: true, mode }};
}})()"""


def _embed_mode_probe(mode: str) -> str:
    if mode == "ask":
        return """(() => {
  const embedCards = document.querySelectorAll('[data-slot="embed-card"]').length;
  const loadYoutube = Array.from(document.querySelectorAll('button')).some(
    (button) => (button.textContent || '').includes('Load YouTube'),
  );
  return {
    ready: embedCards > 0 && loadYoutube,
    embedCards,
    loadYoutube,
  };
})()"""
    if mode == "always":
        return """(() => {
  const embedCards = document.querySelectorAll('[data-slot="embed-card"]').length;
  const loadYoutube = Array.from(document.querySelectorAll('button')).some(
    (button) => (button.textContent || '').includes('Load YouTube'),
  );
  const youtubeIframe = !!document.querySelector('iframe[src*="youtube"]');
  return {
    ready: embedCards > 0 && youtubeIframe && !loadYoutube,
    embedCards,
    loadYoutube,
    youtubeIframe,
  };
})()"""
    return """(() => {
  const embedCards = document.querySelectorAll('[data-slot="embed-card"]').length;
  const plainYoutubeLink = !!document.querySelector('main a[href*="youtube.com/watch"]');
  return {
    ready: embedCards === 0 && plainYoutubeLink,
    embedCards,
    plainYoutubeLink,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
@pytest.mark.parametrize("embed_mode", ["ask", "always", "off"])
def test_link_embed_consent_mode_renders_expected_ui(embed_mode: str) -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_embed_fixture(api_url)
    chat_id = str(seeded["chat_id"])

    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        client.evaluate(page, _set_embed_mode_expression(embed_mode), timeout_sec=15.0)
        reload_mcp_page(client, page)
        state = wait_for_state(
            client,
            page,
            _embed_mode_probe(embed_mode),
            timeout_sec=90.0,
        )
        assert state.get("ready") is True
