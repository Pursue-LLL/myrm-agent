"""Chrome E2E: the undo hint reaches the undo control when Task Steps fold the skill save away.

A turn with more than eight top-level steps shows only its first two and last three behind a "show more" bar. The
skill save of a real turn can sit in the folded stretch, so the hint's "open Task Steps" has to unfold it.
"""

from __future__ import annotations

import time

import pytest

from tests.e2e.test_memory_keyword_recall_live_chrome_e2e import _attach_probe_js
from tests.e2e.test_skill_manage_undo_hint_chrome_e2e import _HINT_READY_JS
from tests.e2e.test_skill_manage_undo_rollback_chrome_e2e import (
    _ATTACH_TIMEOUT_SEC,
    _PAGE_TIMEOUT_MS,
    _TOAST_SUCCESS_JS,
    _fetch_skill_md,
    _seed_chat_with_batch,
    _seed_mutation_batch,
    confirm_rollback,
    describe_chat_page,
    show_rollback_button,
    wait_until_api_is_quiet,
)
from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

# Five finished steps, the skill save, six more: twelve top-level steps, the skill save at index 5 of the folded stretch.
_STEPS_BEFORE_SAVE = 5
_STEPS_AFTER_SAVE = 6

_LONG_TURN_STEP_COUNT_JS = """(() => {
  const state = window.__myrmChatStore?.getState?.();
  const assistants = (state?.messages ?? []).filter((message) => message.role === 'assistant');
  const last = assistants[assistants.length - 1];
  const steps = last?.progressSteps?.length ? last.progressSteps : (last?.metadata?.progressSteps ?? []);
  return { ready: steps.length > 0, count: steps.length };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_undo_hint_unfolds_a_skill_save_hidden_in_a_long_turn_and_the_undo_restores_the_skill() -> None:
    """Hint click -> the folded skill save shows its undo button -> confirm restores the pre-mutation SKILL.md."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    seed = _seed_mutation_batch(api_url)
    batch_id, skill_id = seed["batch_id"], seed["skill_id"]
    marker_v1, marker_v2 = seed["marker_v1"], seed["marker_v2"]
    assert marker_v2 in _fetch_skill_md(api_url, skill_id)

    prepare_e2e_ui_session(api_url)
    chat_id = _seed_chat_with_batch(api_url, batch_id, steps_before=_STEPS_BEFORE_SAVE, steps_after=_STEPS_AFTER_SAVE)
    target_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(target_url, timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=target_url)
        bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=120.0, page_url=target_url)
        assert bridge.get("ready") is True, bridge

        wait_until_api_is_quiet(client, page, api_url, stage="before-chat-load")
        attached = wait_for_state(client, page, _attach_probe_js(chat_id), timeout_sec=_ATTACH_TIMEOUT_SEC, page_url=target_url)
        assert attached.get("ready") is True, attached

        hint_state = wait_for_state(client, page, _HINT_READY_JS, timeout_sec=120.0, page_url=target_url)
        assert hint_state.get("ready") is True, hint_state

        # Without this the test would pass on a short turn that never folds anything.
        turn = wait_for_state(client, page, _LONG_TURN_STEP_COUNT_JS, timeout_sec=30.0, page_url=target_url)
        assert turn.get("count") == _STEPS_BEFORE_SAVE + 1 + _STEPS_AFTER_SAVE, turn

        wait_until_api_is_quiet(client, page, api_url, stage="before-undo")

        # Pressing the hint is the only way to the folded skill save's Undo button here.
        show_rollback_button(client, page, target_url, describe=lambda: describe_chat_page(client, page))
        confirm_rollback(client, page)

        toast_state = wait_for_state(client, page, _TOAST_SUCCESS_JS, timeout_sec=45.0, page_url=target_url)
        assert toast_state.get("ready") is True, toast_state

    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline:
        content = _fetch_skill_md(api_url, skill_id)
        if marker_v1 in content and marker_v2 not in content:
            return
        time.sleep(0.5)
    pytest.fail("Rollback did not restore the v1 marker on SKILL.md")
