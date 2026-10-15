"""Real Chrome MCP E2E: reviewing a queued memory proposal from the chat window badge.

Real-user flow on a chat page:

1. A proposal is waiting for review, so the pending badge shows in the chat window.
2. Clicking the badge opens the review dialog on the first proposal.
3. Edit then accept: the reviewer rewrites the proposal and presses "Save & Accept";
   the stored correction carries the reviewer's text, not the original proposal.
4. Reject: pressing "Reject" drops the proposal and leaves the targeted memory untouched.

Proposals are queued through the same ``submit_pending`` entry that implicit-correction
propagation uses; targets are created through the public memory API with the real
embedding provider from ``.env.test``.
"""

from __future__ import annotations

import json
import re
import uuid

import pytest

from tests.e2e.test_memory_keyword_recall_live_chrome_e2e import _attach_probe_js, _create_agent, _create_chat
from tests.e2e.test_memory_pending_proposal_review_chrome_e2e import (
    _create_semantic_memory,
    _pending_ids,
    _queue_proposal,
    _semantic_memories,
    _trashed_ids,
)
from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)
from tests.support.retrieval_embedding import configured_retrieval_embedding

_EDIT = re.compile(r"^(Edit|编辑)$")
_SAVE_AND_ACCEPT = re.compile(r"^(Save & Accept|保存并接受)$")
_REJECT = re.compile(r"^(Reject|拒绝)$")

_DIALOG_JS = "const dialog = document.querySelector('[role=\"dialog\"]');"


def _open_dialog_js(proposal: str) -> str:
    """Click the badge until the dialog shows ``proposal``; ready once it does."""
    return f"""(() => {{
  {_DIALOG_JS}
  if (dialog && (dialog.textContent || '').includes({json.dumps(proposal)})) return {{ ready: true }};
  const badge = document.querySelector('[data-testid="pending-memory-badge"]');
  if (!dialog && badge) badge.click();
  return {{ ready: false, badge: !!badge, dialog: !!dialog }};
}})()"""


def _dialog_button_js(label: re.Pattern[str]) -> str:
    return f"""(() => {{
  {_DIALOG_JS}
  const label = new RegExp({json.dumps(label.pattern)});
  const button = dialog
    ? Array.from(dialog.querySelectorAll('button')).find((el) => label.test((el.textContent || '').trim()))
    : null;
  if (!button || button.disabled) return {{ ready: false, found: !!button }};
  button.click();
  return {{ ready: true }};
}})()"""


def _type_into_dialog_js(text: str) -> str:
    """Fill the controlled textarea the way a keyboard does so React sees the change."""
    return f"""(() => {{
  {_DIALOG_JS}
  const area = dialog ? dialog.querySelector('textarea') : null;
  if (!area) return {{ ready: false }};
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  setter.call(area, {json.dumps(text)});
  area.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return {{ ready: area.value === {json.dumps(text)} }};
}})()"""


def _dialog_left_proposal_js(proposal: str) -> str:
    """Ready once the dialog no longer shows ``proposal``.

    Resolving a suggestion advances the dialog to the next queued one, so with other pending
    suggestions in the runtime the dialog legitimately stays open on a different suggestion.
    """
    return f"""(() => {{
  {_DIALOG_JS}
  return {{ ready: !dialog || !(dialog.textContent || '').includes({json.dumps(proposal)}) }};
}})()"""


def _open_review_dialog(client: ChromeMcpClient, page: McpPage, proposal: str) -> None:
    wait_for_state(client, page, _open_dialog_js(proposal), timeout_sec=90.0)


def _press(client: ChromeMcpClient, page: McpPage, label: re.Pattern[str]) -> None:
    pressed = wait_for_state(client, page, _dialog_button_js(label), timeout_sec=30.0)
    assert pressed.get("ready") is True, pressed


def _open_chat_page(ui_url: str, chat_id: str):  # noqa: ANN202 - context manager from open_mcp_page
    chat_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route(f"/{chat_id}")
    return chat_url, open_mcp_page(chat_url, timeout_ms=120_000)


def _prepare_chat(api_url: str, suffix: str) -> str:
    agent_id = _create_agent(api_url, f"Memory Dialog Probe {suffix}")
    chat_id = f"e2ependingdialog{suffix}"
    _create_chat(api_url, chat_id, "Memory Pending Dialog E2E", agent_id)
    return chat_id


def _attach(client: ChromeMcpClient, page: McpPage, chat_url: str, chat_id: str) -> None:
    dismiss_blocking_modals(client, page, recover_url=chat_url)
    bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
    assert bridge.get("ready") is True, json.dumps(bridge, ensure_ascii=False)
    attached = wait_for_state(client, page, _attach_probe_js(chat_id), timeout_sec=90.0, page_url=chat_url)
    assert attached.get("ready") is True, json.dumps(attached, ensure_ascii=False)


# exclusive_backend reason: configured_retrieval_embedding mutates global /api/v1/config/retrieval and polls instance-wide /api/v1/memory/pending + semantic memory store.
@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_pending_dialog_edit_then_accept_chrome_e2e() -> None:
    """Editing a proposal in the chat dialog stores the reviewer's text on the correction."""
    api_url = get_e2e_api_url()
    suffix = uuid.uuid4().hex[:8]
    target_text = f"E2E dialog edit {suffix} - user works at ByteDance"
    proposal_text = f"E2E dialog edit {suffix} - user now works at Google"
    edited_text = f"E2E dialog edit {suffix} - user now works at Google as a staff engineer"

    with configured_retrieval_embedding(api_url):
        prepare_e2e_ui_session(api_url)
        target_id = _create_semantic_memory(api_url, target_text)
        pending_id = _queue_proposal(api_url, proposal_text, "correct", target_id)
        chat_id = _prepare_chat(api_url, suffix)

        chat_url, page_ctx = _open_chat_page(get_e2e_ui_url(), chat_id)
        with page_ctx as (client, page):
            _attach(client, page, chat_url, chat_id)
            _open_review_dialog(client, page, proposal_text)
            _press(client, page, _EDIT)
            typed = wait_for_state(client, page, _type_into_dialog_js(edited_text), timeout_sec=30.0)
            assert typed.get("ready") is True, typed
            _press(client, page, _SAVE_AND_ACCEPT)
            closed = wait_for_state(client, page, _dialog_left_proposal_js(proposal_text), timeout_sec=60.0)
            assert closed.get("ready") is True, closed

        memories = _semantic_memories(api_url)
        corrections = [m for m in memories.values() if m.get("correction_of") == target_id]
        assert len(corrections) == 1, memories
        assert corrections[0]["content"] == edited_text, corrections
        assert pending_id not in _pending_ids(api_url)


# exclusive_backend reason: configured_retrieval_embedding mutates global /api/v1/config/retrieval and polls instance-wide /api/v1/memory/pending + semantic memory store.
@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_pending_dialog_reject_keeps_target_chrome_e2e() -> None:
    """Rejecting a delete proposal in the chat dialog leaves the targeted memory active."""
    api_url = get_e2e_api_url()
    suffix = uuid.uuid4().hex[:8]
    target_text = f"E2E dialog reject {suffix} - user lives in Berlin"
    proposal_text = f"E2E dialog reject {suffix} - user no longer lives in Berlin"

    with configured_retrieval_embedding(api_url):
        prepare_e2e_ui_session(api_url)
        target_id = _create_semantic_memory(api_url, target_text)
        pending_id = _queue_proposal(api_url, proposal_text, "delete", target_id)
        chat_id = _prepare_chat(api_url, suffix)

        chat_url, page_ctx = _open_chat_page(get_e2e_ui_url(), chat_id)
        with page_ctx as (client, page):
            _attach(client, page, chat_url, chat_id)
            _open_review_dialog(client, page, proposal_text)
            _press(client, page, _REJECT)
            closed = wait_for_state(client, page, _dialog_left_proposal_js(proposal_text), timeout_sec=60.0)
            assert closed.get("ready") is True, closed

        memories = _semantic_memories(api_url)
        assert memories[target_id]["content"] == target_text, memories
        assert target_id not in _trashed_ids(api_url)
        assert pending_id not in _pending_ids(api_url)
