"""Chrome MCP E2E: Settings allowlist shows pattern entries (Closure Pack UI path)."""

from __future__ import annotations

import pytest

from tests.support.chrome_allowlist_settings_e2e import (
    SETTINGS_SECURITY_SHELL_READY_JS,
    allowlist_pattern_visible_js,
)
from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)


@pytest.fixture(autouse=True)
def _seed_live_allowlist_pattern_row() -> None:
    api_base = get_e2e_api_url()
    seeded = http_json(
        "POST",
        f"{api_base}/api/v1/security/allowlist/test/seed-pattern-fixture",
    )
    assert isinstance(seeded, dict) and seeded.get("command_pattern") == "npm install *", seeded

    listed = http_json("GET", f"{api_base}/api/v1/security/allowlist")
    assert isinstance(listed, dict)
    rows = listed.get("data")
    assert isinstance(rows, list) and len(rows) == 1
    row = rows[0]
    assert row.get("granularity") == "pattern"
    assert row.get("command_pattern") == "npm install *"

    yield

    http_json(
        "DELETE",
        f"{api_base}/api/v1/security/allowlist/test/clear-pattern-fixture",
        expected_statuses=frozenset({200, 204}),
    )


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.timeout(240)
def test_settings_security_shows_pattern_allowlist_entry() -> None:
    warm_ui_route("/settings/security")
    ui_base = get_e2e_ui_url()
    with open_mcp_page(f"{ui_base}/settings/security", timeout_ms=90_000) as (client, page):
        shell = wait_for_state(client, page, SETTINGS_SECURITY_SHELL_READY_JS, timeout_sec=90.0)
        assert shell.get("ready") is True, shell

        visible = wait_for_state(client, page, allowlist_pattern_visible_js(), timeout_sec=60.0)
        assert visible.get("ready") is True, visible
