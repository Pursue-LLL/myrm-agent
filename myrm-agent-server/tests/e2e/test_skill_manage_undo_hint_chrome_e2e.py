"""Chrome E2E: skill manage undo hint opens Task Steps.

Set ``E2E_SKILL_MANAGE_UNDO_CHAT_PATH`` to a chat URL path (e.g. ``/chat/<id>``)
whose latest assistant message already has a successful ``skill_manage_tool`` step
with ``skill_mutation_batch_id`` (live agent turn or fixture seed).

Run::

    E2E_SKILL_MANAGE_UNDO_CHAT_PATH=/chat/<uuid> ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_skill_manage_undo_hint_chrome_e2e.py
"""

from __future__ import annotations

import os

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_skill_manage_undo_hint_expands_task_steps() -> None:
    chat_path = os.environ.get("E2E_SKILL_MANAGE_UNDO_CHAT_PATH", "").strip()
    if not chat_path:
        pytest.skip("Set E2E_SKILL_MANAGE_UNDO_CHAT_PATH to a chat with skill_manage undo hint")

    prepare_e2e_ui_session()
    page = open_mcp_page(f"{get_e2e_ui_url()}{chat_path}")
    try:
        warm_ui_route(page, chat_path)
        dismiss_blocking_modals(page)
        wait_for_state(page, '[data-testid="skill-manage-undo-hint"]', timeout_ms=120_000)

        toggle = page.query_selector('[data-testid="progress-steps-toggle"]')
        assert toggle is not None
        if toggle.get_attribute("data-expanded") != "true":
            hint_button = page.query_selector('[data-testid="skill-manage-undo-hint-open-steps"]')
            assert hint_button is not None
            hint_button.click()
            wait_for_state(page, '[data-testid="progress-steps-toggle"][data-expanded="true"]', timeout_ms=15_000)

        rollback = page.query_selector('[data-testid="skill-manage-rollback-button"]')
        assert rollback is not None
    finally:
        page.close()
