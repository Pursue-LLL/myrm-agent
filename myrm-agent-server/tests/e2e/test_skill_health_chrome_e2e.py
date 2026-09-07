"""Real Chrome MCP E2E for SkillHealthPanel in /journey."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_ui_url,
    open_settings_subroute,
    wait_for_state,
)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_skill_health_governance_panel_in_journey_page() -> None:
    """Verify SkillHealthPanel tabs and governance recommendations in /journey."""
    with open_settings_subroute("/journey") as (client, page):
        journey_url = f"{get_e2e_ui_url().rstrip('/')}/journey"
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
              return { ready: hasHealthHeader && filterAll && filterAttention, hasHealthHeader, filterAll, filterAttention };
            })()""",
            timeout_sec=60.0,
            page_url=journey_url,
        )
        assert state.get("ready") is True
