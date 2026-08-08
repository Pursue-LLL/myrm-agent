"""Chrome E2E (NAMESPACE_WRITE): real WBBench download through the Eval Lab UI.

Walks the real user flow in the browser: open the Eval Lab page, click the
Download button on the office card (smallest subset, ~10 MB), and wait for the
UI to flip to the downloaded state once the backend finishes the real
HuggingFace download, checksum verify and install. Uses a private backend so
the shared stack is never polluted.
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
    click_subset_download_js,
    restore_eval_lab_route,
    subset_downloaded_js,
)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wb_bench_download_office_real_flow_chrome_e2e() -> None:
    """Clicking Download on the office card completes a real HF download via the UI."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route(EVAL_LAB_PATH)

    with open_mcp_page(f"{ui_url}{EVAL_LAB_PATH}", timeout_ms=120_000) as (
        client,
        page,
    ):
        restore_eval_lab_route(client, page, f"{ui_url}{EVAL_LAB_PATH}")
        dismiss_blocking_modals(client, page)
        sources_ready = wait_for_state(
            client, page, SOURCES_READY_JS, timeout_sec=120.0
        )
        assert sources_ready.get("ready") is True, sources_ready

        clicked = client.evaluate(page, click_subset_download_js("WBBench Office"))
        assert clicked.get("ok") is True, clicked

        downloaded = wait_for_state(
            client, page, subset_downloaded_js("WBBench Office"), timeout_sec=300.0
        )
        assert downloaded.get("ready") is True, downloaded
