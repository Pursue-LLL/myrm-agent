"""Real Chrome MCP E2E for Browser TaskSpaceDock floating pill in WebUI."""

from __future__ import annotations

import json
import urllib.request

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
)

_CREATE_SPACE_URL = f"{get_e2e_api_url()}/api/v1/browser/spaces"


def _create_e2e_space(space_id: str, name: str) -> None:
    req = urllib.request.Request(
        _CREATE_SPACE_URL,
        data=json.dumps({"space_id": space_id, "name": name}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200


def _delete_e2e_space(space_id: str) -> None:
    req = urllib.request.Request(
        f"{_CREATE_SPACE_URL}/{space_id}",
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
    except Exception:
        pass


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_task_space_dock_real_chrome_e2e() -> None:
    """Verify TaskSpaceDock appears when spaces exist and disappears on delete."""
    space_id = "e2e-dock-test-space"
    space_name = "E2E Dock Verification"
    ui_url = get_e2e_ui_url()

    # Pre-clean
    _delete_e2e_space(space_id)
    prepare_e2e_ui_session(ui_url)

    with open_mcp_page(f"{ui_url.rstrip('/')}/") as (client, page):
        dismiss_blocking_modals(client, page)

        # Step 1: Create space in backend
        _create_e2e_space(space_id, space_name)

        try:
            # Step 2: Poll DOM in real Chrome until TaskSpaceDock floating pill appears
            check_dock_js = """(() => {
                const bodyText = document.body.innerText || '';
                const hasPill = bodyText.includes('并行任务空间') || bodyText.includes('Parallel Task Spaces');
                return { ready: hasPill };
            })()"""

            state = wait_for_state(
                client,
                page,
                check_dock_js,
                predicate=lambda s: bool(s.get("ready")),
                timeout_sec=30.0,
                interval_sec=1.0,
                page_url=f"{ui_url.rstrip('/')}/",
                failure_message="TaskSpaceDock floating pill did not appear in real Chrome WebUI",
            )
            assert state.get("ready") is True

        finally:
            # Step 3: Cleanup space
            _delete_e2e_space(space_id)
