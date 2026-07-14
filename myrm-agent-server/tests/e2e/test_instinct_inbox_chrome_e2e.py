"""Real Chrome MCP E2E for the per-agent Instinct Inbox."""

from __future__ import annotations

import urllib.parse

import pytest

from tests.support.chrome_mcp_e2e import API_URL, BASE_URL, http_json, open_mcp_page, wait_for_state

_INBOX_STATE = """(() => {
  const panel = document.querySelector('[data-testid="instinct-inbox-panel"]');
  const empty = document.querySelector('[data-testid="instinct-inbox-empty"]');
  if (!panel && !empty) {
    const tab = Array.from(document.querySelectorAll('button')).find((button) =>
      /洞察|Insights/i.test(button.textContent || '')
    );
    if (tab) tab.click();
  }
  const cards = Array.from(document.querySelectorAll('[data-testid="instinct-draft-card"]'));
  return {
    ready: !!panel,
    names: cards.map((card) => card.getAttribute('data-draft-name') || ''),
    cards: cards.length,
  };
})()"""


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_instinct_inbox_renders_and_rejects_seeded_drafts() -> None:
    seed_url = f"{API_URL}/api/v1/skills/drafts/test/seed-mock?" + urllib.parse.urlencode({"agent_id": "builtin-general"})
    seeded = http_json("POST", seed_url)
    assert isinstance(seeded, dict)
    created_ids = seeded.get("created_ids")
    assert isinstance(created_ids, list) and all(isinstance(item, str) for item in created_ids)

    try:
        with open_mcp_page(f"{BASE_URL}/settings/agents?agentId=builtin-general") as (client, page):
            state = wait_for_state(client, page, _INBOX_STATE)
            names = state.get("names")
            assert isinstance(names, list)
            assert {"test-frontend-approve", "test-frontend-reject"}.issubset(set(names))

            for remaining in (1, 0):
                result = client.evaluate(
                    page,
                    """(() => {
                      const button = document.querySelector('[data-testid="instinct-reject-btn"]');
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
                f"{API_URL}/api/v1/skills/drafts/{draft_id}/reject",
                expected_statuses=frozenset({200, 404}),
            )
