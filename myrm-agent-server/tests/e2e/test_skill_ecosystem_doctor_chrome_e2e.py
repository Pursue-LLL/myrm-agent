"""Chrome MCP E2E: the System Doctor page shows the skill-ecosystem probe row.

The skill probe (`SkillQualityHealthDiagnostic`) is read by someone who opens the sidebar's
"System Doctor" entry and looks for a skill-ecosystem verdict. Nothing in the browser suite covered
that page, so a probe that stopped reaching it — a renamed component, a dropped field, a page that
never renders its rows — would stay invisible.

This runs the real page against the real backend: the row it asserts on is the one
`GET /health/doctor` returns, not a stubbed payload.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_ui_url,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

# The dashboard fetches /health/doctor itself, so "ready" also means the payload landed: without rows
# the page shows its empty state and the skill row would be missing for a reason unrelated to the probe.
_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  return {
    ready: location.pathname.startsWith('/health') && text.length > 40,
    pathname: location.pathname,
    bodyLength: text.length,
  };
})()"""

# Matches the row by its rendered title. Both locales are accepted so the assertion does not depend on
# the language the E2E browser happens to use.
_SKILL_ROW_JS = """(() => {
  const rows = Array.from(document.querySelectorAll('*')).filter((el) => {
    const own = el.childElementCount === 0 ? el.textContent || '' : '';
    return /Skill ecosystem|技能生态/.test(own);
  });
  const row = rows.length
    ? rows[0].closest('[data-doctor-row]') || rows[0].closest('div')
    : null;
  const text = document.body?.innerText || '';
  return {
    ready: rows.length > 0,
    rowCount: rows.length,
    // The verdict line the row prints next to the title (pass/warn/fail wording comes from the probe).
    excerpt: (row?.innerText || '').slice(0, 400),
    hasSkillEcosystem: /Skill ecosystem|技能生态/.test(text),
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_skill_ecosystem_row_renders_on_the_system_doctor_page() -> None:
    """The sidebar's System Doctor page must surface the skill-ecosystem probe as a real row."""
    warm_ui_route("/health", timeout_sec=_warm_ui_parallel_wait_sec(180.0))

    health_url = f"{get_e2e_ui_url().rstrip('/')}/health"
    with open_mcp_page(health_url) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page)

        ready = wait_for_state(
            client,
            page,
            _READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert ready.get("ready") is True, ready

        row = wait_for_state(
            client,
            page,
            _SKILL_ROW_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert row.get("ready") is True, row
        assert row.get("hasSkillEcosystem") is True, row
        # The row prints the probe's own verdict text; an empty excerpt means the title rendered
        # without the report behind it.
        assert str(row.get("excerpt") or "").strip(), row
