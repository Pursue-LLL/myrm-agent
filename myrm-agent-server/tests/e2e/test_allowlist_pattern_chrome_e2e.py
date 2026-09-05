"""Chrome MCP E2E: Settings allowlist shows pattern entries (Closure Pack UI path)."""

from __future__ import annotations

import pytest

from tests.support.chrome_allowlist_settings_e2e import (
    REFRESH_ALLOWLIST_JS,
    SETTINGS_SECURITY_SHELL_READY_JS,
    allowlist_pattern_visible_js,
)
from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)


def _seed_allowlist_pattern_row(client, page) -> None:
    """Seed via page fetch using the runtime api base so UI and DB share the pinned stack."""
    result = client.evaluate(
        page,
        """(() => {
  const base = window.__MYRM_E2E_RUNTIME__?.apiBase || window.__MYRM_E2E_API_BASE__ || '';
  return fetch(`${base}/api/v1/security/allowlist/test/seed-pattern-fixture`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
    .then(async (res) => {
      const body = await res.json().catch(() => ({}));
      return {
        ok: res.ok,
        status: res.status,
        command_pattern: body?.command_pattern ?? body?.data?.command_pattern ?? null,
        entry_id: body?.entry_id ?? body?.data?.entry_id ?? null,
      };
    })
    .catch((err) => ({ ok: false, err: String(err) }));
})()""",
        timeout_sec=30.0,
    )
    assert isinstance(result, dict), result
    assert result.get("ok") is True, result
    assert result.get("command_pattern") == "npm install *", result
    assert str(result.get("entry_id") or "").strip(), result


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_settings_security_shows_pattern_allowlist_entry() -> None:
    api_base = get_e2e_api_url()
    warm_ui_route("/settings/security")
    with open_settings_subroute("/settings/security", timeout_ms=90_000) as (client, page):
        shell = wait_for_state(client, page, SETTINGS_SECURITY_SHELL_READY_JS, timeout_sec=90.0)
        assert shell.get("ready") is True, shell

        _seed_allowlist_pattern_row(client, page)
        refreshed = client.evaluate(page, REFRESH_ALLOWLIST_JS, timeout_sec=15.0)
        assert isinstance(refreshed, dict) and refreshed.get("ok") is True, refreshed

        visible = wait_for_state(client, page, allowlist_pattern_visible_js(), timeout_sec=60.0)
        assert visible.get("ready") is True, visible

        # Also verify time-bound seed entry displays time-bound badge
        client.evaluate(
            page,
            """(() => {
  const base = window.__MYRM_E2E_RUNTIME__?.apiBase || window.__MYRM_E2E_API_BASE__ || '';
  return fetch(`${base}/api/v1/security/allowlist/test/seed-pattern-fixture?ttl_seconds=3600`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  }).then(r => r.json()).catch(() => ({}));
})()""",
            timeout_sec=15.0,
        )
        client.evaluate(page, REFRESH_ALLOWLIST_JS, timeout_sec=15.0)
        time_bound_check = wait_for_state(
            client,
            page,
            """(() => {
  const text = document.body?.innerText || '';
  const hasTimeBound = /Time-bound|限时|1h|15m/i.test(text);
  return { ready: hasTimeBound, sample: text.slice(0, 500) };
})()""",
            timeout_sec=30.0,
        )
        assert time_bound_check.get("ready") is True, time_bound_check

    http_json(
        "DELETE",
        f"{api_base}/api/v1/security/allowlist/test/clear-pattern-fixture",
        expected_statuses=frozenset({200, 204}),
    )
