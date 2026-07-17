"""Real Chrome MCP E2E for the per-agent Instinct Inbox."""

from __future__ import annotations

import urllib.parse

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
)

_INBOX_STATE = """(() => {
  try {
    window.resizeTo(1280, 900);
  } catch {
    // ignore
  }
  const panel = document.querySelector('[data-testid="instinct-inbox-panel"]');
  const empty = document.querySelector('[data-testid="instinct-inbox-empty"]');
  if (!panel && !empty) {
    const tab = Array.from(document.querySelectorAll('button,[role="tab"]')).find((button) =>
      /洞察|Insights/i.test(button.textContent || '')
    );
    if (tab) tab.click();
  }
  const cards = Array.from(document.querySelectorAll('[data-testid="instinct-draft-card"]'));
  return {
    ready: !!panel || cards.length > 0,
    names: cards.map((card) => card.getAttribute('data-draft-name') || ''),
    cards: cards.length,
  };
})()"""


@pytest.mark.chrome_e2e(lane="LIVE_AGENT")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_instinct_inbox_renders_and_rejects_seeded_drafts() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seed_url = f"{api_url}/api/v1/skills/drafts/test/seed-mock?" + urllib.parse.urlencode(
        {"agent_id": "builtin-general"}
    )
    seeded = http_json("POST", seed_url)
    assert isinstance(seeded, dict)
    created_ids = seeded.get("created_ids")
    assert isinstance(created_ids, list) and all(isinstance(item, str) for item in created_ids)

    try:
        with open_mcp_page(f"{ui_url}/settings/agents?agentId=builtin-general") as (client, page):
            state = wait_for_state(client, page, _INBOX_STATE, timeout_sec=120.0)
            names = state.get("names")
            assert isinstance(names, list)
            assert {"test-frontend-approve", "test-frontend-reject"}.issubset(set(names))

            for remaining in (1, 0):
                wait_for_state(
                    client,
                    page,
                    """(() => {
                      const button = document.querySelector('[data-testid="instinct-dismiss-btn"]');
                      return { ready: !!button, hasButton: !!button };
                    })()""",
                    timeout_sec=90.0,
                )
                result = client.evaluate(
                    page,
                    """(() => {
                      const button = document.querySelector('[data-testid="instinct-dismiss-btn"]');
                      if (!button) return { clicked: false };
                      button.click();
                      return { clicked: true };
                    })()""",
                    timeout_sec=5.0,
                )
                assert isinstance(result, dict) and result.get("clicked") is True
                wait_for_state(
                    client,
                    page,
                    f"""(() => {{
                      const count = document.querySelectorAll('[data-testid="instinct-draft-card"]').length;
                      return {{ ready: count === {remaining}, count }};
                    }})()""",
                )
    finally:
        for draft_id in created_ids:
            http_json(
                "POST",
                f"{api_url}/api/v1/skills/drafts/{draft_id}/reject",
                expected_statuses=frozenset({200, 404, 400}),
            )
