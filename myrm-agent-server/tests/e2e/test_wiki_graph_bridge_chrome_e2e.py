"""Chrome E2E: Library graph tab + insights panel + Settings graph entry."""

from __future__ import annotations

import os
import sys

import pytest

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    open_wiki_settings_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_GRAPH_INSIGHTS_PANEL_JS = """(() => ({
  ready:
    location.pathname.endsWith('/library') &&
    !!document.querySelector('[data-testid="wiki-graph-insights-panel"]'),
}))()"""

_GRAPH_VIEW_JS = """(() => ({
  ready:
    location.pathname.endsWith('/library') &&
    (
      !!document.querySelector('[data-testid="wiki-graph-insights-panel"]') ||
      !!document.querySelector('[data-testid="wiki-graph-empty"]')
    ),
  hasInsights: !!document.querySelector('[data-testid="wiki-graph-insights-panel"]'),
  hasEmpty: !!document.querySelector('[data-testid="wiki-graph-empty"]'),
}))()"""

_WIKI_GO_GRAPH_BTN_JS = """(() => ({
  ready:
    location.pathname.endsWith('/settings/wiki') &&
    !!document.querySelector('[data-testid="wiki-go-graph-btn"]'),
  hasBtn: !!document.querySelector('[data-testid="wiki-go-graph-btn"]'),
}))()"""


def _run_graph_bridge_assertions(api_url: str, ui_url: str) -> None:
    insights = http_json("GET", f"{api_url.rstrip('/')}/api/v1/wiki/graph/insights")
    assert isinstance(insights, dict)
    assert "knowledge_gaps" in insights
    assert "unexpected_connections" in insights
    assert "communities" in insights

    graph = http_json("GET", f"{api_url.rstrip('/')}/api/v1/wiki/graph")
    assert isinstance(graph, dict)
    assert "nodes" in graph
    assert "edges" in graph

    warm_ui_route("/settings")
    graph_page_url = f"{ui_url.rstrip('/')}/library?tab=graph"
    with open_mcp_page(
        graph_page_url,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    ) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=graph_page_url)
        graph_state = wait_for_state(
            client,
            page,
            _GRAPH_VIEW_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(60.0),
            page_url=graph_page_url,
        )
        assert graph_state.get("ready") is True, graph_state
        insights_state = wait_for_state(
            client,
            page,
            _GRAPH_INSIGHTS_PANEL_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(45.0),
            page_url=graph_page_url,
        )
        assert insights_state.get("ready") is True, insights_state

    wiki_page_url = f"{ui_url.rstrip('/')}/settings/wiki"
    with open_wiki_settings_mcp_page(
        wiki_page_url,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    ) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=wiki_page_url)
        btn_state = client.evaluate(page, _WIKI_GO_GRAPH_BTN_JS, timeout_sec=15.0)
        if isinstance(btn_state, dict) and btn_state.get("hasBtn"):
            entry = wait_for_state(
                client,
                page,
                _WIKI_GO_GRAPH_BTN_JS,
                timeout_sec=_warm_ui_parallel_wait_sec(30.0),
                page_url=wiki_page_url,
            )
            assert entry.get("ready") is True, entry


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wiki_graph_bridge_library_and_settings_entry() -> None:
    """Graph insights API + Library graph UI + Settings graph CTA when vault ready."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_graph_bridge_assertions(get_e2e_api_url(), ui_url)
