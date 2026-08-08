"""Chrome E2E (READ): WorkBuddy Bench dataset cards render on the Eval Lab page.

Opens the Eval Lab WebUI in a real browser and verifies that the four WBBench
subset cards (Code / Web / Office / Security) with their task counts render
from the live sources API.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)
from tests.support.wb_bench_e2e_helpers import (
    EVAL_LAB_PATH,
    SOURCES_READY_JS,
    restore_eval_lab_route,
)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_wb_bench_sources_render_chrome_e2e() -> None:
    """The Eval Lab page renders all four WBBench dataset cards from the API."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route(EVAL_LAB_PATH)

    with open_mcp_page(f"{ui_url}{EVAL_LAB_PATH}", timeout_ms=120_000) as (
        client,
        page,
    ):
        restore_eval_lab_route(client, page, f"{ui_url}{EVAL_LAB_PATH}")
        dismiss_blocking_modals(client, page)
        ready = wait_for_state(client, page, SOURCES_READY_JS, timeout_sec=120.0)
        assert ready.get("ready") is True, ready
