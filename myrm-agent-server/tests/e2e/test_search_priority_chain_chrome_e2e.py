"""Chrome E2E signoff: search priority chain (dual-provider config + runtime chain shape)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    fetch_config_value,
    get_e2e_api_url,
    put_config_value,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_ui_url,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
    _warm_ui_parallel_wait_sec,
)

_PRIORITY_CHAIN_PAYLOAD = {
    "searchServiceConfigs": [
        {
            "id": "e2e-priority-tavily",
            "name": "E2E Tavily Primary",
            "enabled": True,
            "priority": 1,
            "search_service": "tavily",
            "api_key": "tvly-invalid-for-chain-signoff",
            "createdAt": int(time.time() * 1000),
        },
        {
            "id": "e2e-priority-perplexity",
            "name": "E2E Perplexity Fallback",
            "enabled": True,
            "priority": 2,
            "search_service": "perplexity",
            "api_key": "pplx-invalid-for-chain-signoff",
            "createdAt": int(time.time() * 1000) + 1,
        },
    ]
}

_SETTINGS_PRIORITY_VISIBLE_JS = """(() => {
  const body = document.body?.innerText ?? '';
  const fetchErrorVisible = /无法连接服务器|Unable to connect to the server/i.test(body);
  const hasP1 = /Priority\\s*1|优先级\\s*1/u.test(body);
  const hasP2 = /Priority\\s*2|优先级\\s*2/u.test(body);
  const cards = Array.from(document.querySelectorAll('[class*="rounded-xl"][class*="border"]'));
  const searchCards = cards.filter((node) => /Priority\\s*[12]|优先级\\s*[12]/u.test(node.textContent || ''));
  return {
    ready:
      location.pathname.includes('/settings/search') &&
      !fetchErrorVisible &&
      hasP1 &&
      hasP2 &&
      searchCards.length >= 2,
    fetchErrorVisible,
    hasP1,
    hasP2,
    searchCardCount: searchCards.length,
    path: location.pathname,
    sample: body.slice(0, 1200),
  };
})()"""


def _assert_provider_chain_from_api(api_base: str) -> None:
    from app.core.channel_bridge.config_parsers import extract_active_search_config

    stored = fetch_config_value("searchServices", api_url=api_base)
    configs = stored.get("searchServiceConfigs")
    assert isinstance(configs, list) and len(configs) >= 2, stored

    priorities = sorted(
        int(item["priority"])
        for item in configs
        if isinstance(item, dict) and item.get("enabled") is True and "priority" in item
    )
    assert priorities[:2] == [
        1,
        2,
    ], f"expected enabled priorities 1,2 got {priorities!r}; stored={stored!r}"

    active = extract_active_search_config(stored)
    assert active is not None
    assert active.provider_chain is not None
    assert len(active.provider_chain) == 2
    assert active.provider_chain[0].search_service == "tavily"
    assert active.provider_chain[1].search_service == "perplexity"


@pytest.mark.integration
def test_search_priority_chain_persists_via_omni_config_api() -> None:
    """API signoff: dual enabled configs with unique priority → provider_chain length 2."""
    api_base = get_e2e_api_url()
    if not wait_e2e_provider_ready(api_url=api_base):
        pytest.skip("E2E backend not ready for search priority chain API signoff")

    backup = fetch_config_value("searchServices", api_url=api_base)
    try:
        put_config_value("searchServices", _PRIORITY_CHAIN_PAYLOAD, api_url=api_base)
        _assert_provider_chain_from_api(api_base)
    finally:
        if backup:
            put_config_value("searchServices", backup, api_url=api_base)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE", access_scope="GLOBAL_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_search_priority_chain_settings_ui_shows_priorities() -> None:
    """PRIVATE GLOBAL_WRITE: isolated backend config + settings/search priority UI."""
    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url().rstrip("/")
    if not wait_e2e_provider_ready(api_url=api_base):
        pytest.skip("E2E backend not ready for search priority chain Chrome signoff")

    backup = fetch_config_value("searchServices", api_url=api_base)
    settings_url = f"{ui_base}/settings/search"
    try:
        put_config_value("searchServices", _PRIORITY_CHAIN_PAYLOAD, api_url=api_base)
        _assert_provider_chain_from_api(api_base)

        warm_ui_route("/settings/search")
        with open_mcp_page(settings_url, timeout_ms=90_000) as (client, page):
            dismiss_blocking_modals(client, page)
            client.navigate(page, settings_url, timeout_ms=90_000)
            dismiss_blocking_modals(client, page)
            visible = wait_for_state(
                client,
                page,
                _SETTINGS_PRIORITY_VISIBLE_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(120.0),
            )
            assert visible.get("ready") is True, json.dumps(visible, ensure_ascii=False)
            assert visible.get("fetchErrorVisible") is not True, visible
            assert int(visible.get("searchCardCount") or 0) >= 2, visible
    finally:
        if backup:
            put_config_value("searchServices", backup, api_url=api_base)
