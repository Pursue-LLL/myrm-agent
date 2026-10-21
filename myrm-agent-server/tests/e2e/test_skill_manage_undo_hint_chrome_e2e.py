"""Chrome E2E: skill manage undo hint opens Task Steps and shows rollback control."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.e2e.test_memory_keyword_recall_live_chrome_e2e import _attach_probe_js
from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_PAGE_TIMEOUT_MS = 180_000

_HINT_READY_JS = """(() => ({
  ready: !!document.querySelector('[data-testid="skill-manage-undo-hint"]'),
}))()"""

_CLICK_OPEN_STEPS_JS = """(() => {
  const btn = document.querySelector('[data-testid="skill-manage-undo-hint-open-steps"]');
  if (!btn) return { ok: false, err: 'missing-hint-button' };
  btn.click();
  return { ok: true };
})()"""

_STEPS_EXPANDED_JS = """(() => ({
  ready:
    document.querySelector('[data-testid="progress-steps-toggle"]')?.getAttribute('data-expanded') === 'true',
}))()"""

_ROLLBACK_VISIBLE_JS = """(() => ({
  ready: !!document.querySelector('[data-testid="skill-manage-rollback-button"]'),
}))()"""


def _seed_skill_manage_undo_fixture(api_base: str) -> str:
    """Seed chat whose assistant message carries a successful skill_manage progress step."""
    batch_id = str(uuid.uuid4())
    chat_id = f"e2eundo_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).replace(microsecond=0)
    footer = json.dumps({"batch_id": batch_id}, separators=(",", ":"))
    progress_steps = [
        {
            "step_key": "tool_skill_manage_tool",
            "tool_name": "skill_manage_tool",
            "status": "success",
            "skill_mutation_batch_id": batch_id,
            "items": f"Batch applied successfully (batch_id={batch_id}).\nmyrm_skill_batch:{footer}",
        }
    ]
    messages = [
        {
            "messageId": f"msg-user-{chat_id}",
            "chatId": chat_id,
            "role": "user",
            "content": "Update my test skill please.",
            "createdAt": now.isoformat(),
        },
        {
            "messageId": f"msg-asst-{chat_id}",
            "chatId": chat_id,
            "role": "assistant",
            "content": "Applied skill changes in a batch.",
            "createdAt": (now + timedelta(seconds=1)).isoformat(),
            "metadata": {"progressSteps": progress_steps},
        },
    ]
    create_payload = {
        "chat_id": chat_id,
        "title": "E2E Skill Manage Undo Hint",
        "action_mode": "agent",
        "is_incognito": False,
        "messages": messages,
    }
    http_json("POST", f"{api_base}/api/v1/chats/", body=create_payload)
    return chat_id


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_skill_manage_undo_hint_expands_task_steps() -> None:
    """Hint card expands Task Steps; rollback button is visible for a seeded successful batch."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    chat_path = os.environ.get("E2E_SKILL_MANAGE_UNDO_CHAT_PATH", "").strip()
    if chat_path:
        if not chat_path.startswith("/"):
            chat_path = f"/{chat_path.lstrip('/')}"
        chat_id = chat_path.strip("/").split("/")[-1]
    else:
        chat_id = _seed_skill_manage_undo_fixture(api_url)
        chat_path = f"/{chat_id}"

    target_url = f"{ui_url.rstrip('/')}/{chat_id}"
    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(target_url, timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=target_url)
        bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=120.0, page_url=target_url)
        assert bridge.get("ready") is True, bridge

        attached = wait_for_state(
            client,
            page,
            _attach_probe_js(chat_id),
            timeout_sec=120.0,
            page_url=target_url,
        )
        assert attached.get("ready") is True, attached

        hint_state = wait_for_state(client, page, _HINT_READY_JS, timeout_sec=120.0, page_url=target_url)
        assert hint_state.get("ready") is True, hint_state

        expanded_raw = client.evaluate(page, _STEPS_EXPANDED_JS, timeout_sec=10.0)
        expanded = expanded_raw if isinstance(expanded_raw, dict) else {}
        if expanded.get("ready") is not True:
            click_res = client.evaluate(page, _CLICK_OPEN_STEPS_JS, timeout_sec=10.0)
            assert isinstance(click_res, dict) and click_res.get("ok") is True, click_res
            expanded = wait_for_state(client, page, _STEPS_EXPANDED_JS, timeout_sec=15.0, page_url=target_url)
            assert expanded.get("ready") is True, expanded

        rollback_state = wait_for_state(client, page, _ROLLBACK_VISIBLE_JS, timeout_sec=30.0, page_url=target_url)
        assert rollback_state.get("ready") is True, rollback_state
