"""Chrome READ E2E: DPSEAG-Lite delegation permissions on Settings security page."""

from __future__ import annotations

import pytest

from tests.support.chrome_allowlist_settings_e2e import SETTINGS_SECURITY_SHELL_READY_JS
from tests.support.chrome_delegation_permissions_e2e import (
    _DELEGATION_GUIDE_SCROLL_JS,
    DELEGATION_PERMISSION_TYPES_IN_RULES_JS,
    DELEGATION_PERMISSIONS_GUIDE_READY_JS,
)
from tests.support.chrome_mcp_e2e import (
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.timeout(240)
def test_settings_security_shows_delegation_permission_guide_and_types() -> None:
    """Lane-B: WebUI /settings/security renders DPSEAG dual-key guide + permission labels."""
    warm_ui_route("/settings/security")
    with open_settings_subroute("/settings/security", timeout_ms=90_000) as (client, page):
        shell = wait_for_state(client, page, SETTINGS_SECURITY_SHELL_READY_JS, timeout_sec=90.0)
        assert shell.get("ready") is True, shell

        client.evaluate(page, _DELEGATION_GUIDE_SCROLL_JS, timeout_sec=15.0)

        guide = wait_for_state(
            client,
            page,
            DELEGATION_PERMISSIONS_GUIDE_READY_JS,
            timeout_sec=60.0,
        )
        assert guide.get("ready") is True, guide

        types_visible = wait_for_state(
            client,
            page,
            DELEGATION_PERMISSION_TYPES_IN_RULES_JS,
            timeout_sec=60.0,
        )
        assert types_visible.get("ready") is True, types_visible
