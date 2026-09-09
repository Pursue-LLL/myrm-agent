"""Real Chrome MCP E2E for SkillHealthPanel in /journey."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_ui_url,
    open_mcp_page,
    wait_for_state,
)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_skill_health_governance_panel_in_journey_page() -> None:
    """Verify SkillHealthPanel tabs and governance recommendations in /journey."""
    journey_url = f"{get_e2e_ui_url().rstrip('/')}/journey"
    with open_mcp_page(journey_url) as (client, page):
        state = wait_for_state(
            client,
            page,
            """(() => {
              const bodyText = document.body.innerText || '';
              const hasHealthHeader = /Skill Health|技能健康度/i.test(bodyText);
              const filterAll = Array.from(document.querySelectorAll('button')).some((b) =>
                /^(All|全部)/i.test((b.textContent || '').trim())
              );
              const filterAttention = Array.from(document.querySelectorAll('button')).some((b) =>
                /Needs Attention|待治理/i.test(b.textContent || '')
              );
              const filterHealthy = Array.from(document.querySelectorAll('button')).some((b) =>
                /Healthy|健康/i.test(b.textContent || '')
              );
              return { ready: hasHealthHeader && filterAll && filterAttention && filterHealthy, hasHealthHeader, filterAll, filterAttention, filterHealthy };
            })()""",
            timeout_sec=60.0,
            page_url=journey_url,
        )
        assert state.get("ready") is True
