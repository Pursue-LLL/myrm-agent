"""Chrome E2E: Async user message card rendering, steer interaction, and Hermes #64578 fallback."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    ensure_desktop_viewport,
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

_CARD_RENDER_READY_JS = """(() => {
  const textMatch = (document.body?.innerText || '').includes('GAAP vs Non-GAAP');
  const recoMatch = (document.body?.innerText || '').includes('Adopt Non-GAAP');
  return {
    ready: textMatch && recoMatch,
    textMatch,
    recoMatch,
  };
})()"""

_CLICK_ADOPT_BUTTON_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const adoptBtn = buttons.find(b => 
    (b.textContent || '').includes('Adopt Non-GAAP') || 
    (b.textContent || '').includes('采纳')
  );
  if (!adoptBtn) return { ok: false, err: 'adopt-button-not-found' };
  adoptBtn.click();
  return { ok: true, text: adoptBtn.textContent };
})()"""

_CHECK_INPUT_FALLBACK_JS = """(() => {
  const inputEl = document.querySelector('[data-chat-input]');
  if (!inputEl) return { ready: false, err: 'no-input' };
  const val = inputEl.value || '';
  return {
    ready: val.includes('Adopt Non-GAAP'),
    value: val,
  };
})()"""


def _seed_async_user_message_fixture(api_base: str) -> str:
    """Seed a conversation with an assistant message containing asyncUserMessages."""
    chat_id = f"e2esteer_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).replace(microsecond=0)
    messages = [
        {
            "messageId": f"msg-user-{chat_id}",
            "chatId": chat_id,
            "role": "user",
            "content": "Please start the financial audit pipeline.",
            "createdAt": now.isoformat(),
        },
        {
            "messageId": f"msg-asst-{chat_id}",
            "chatId": chat_id,
            "role": "assistant",
            "content": "Running financial verification pipeline...",
            "createdAt": (now + timedelta(seconds=1)).isoformat(),
            "metadata": {
                "asyncUserMessages": [
                    {
                        "callId": "call_gaap_audit_e2e",
                        "message": "Ambiguity found: GAAP vs Non-GAAP accounting standard.",
                        "category": "question",
                        "recommendation": "Adopt Non-GAAP standardized audit report",
                        "status": "pending",
                        "suggestedReplies": [
                            "Adopt Non-GAAP standardized audit report",
                            "Stick to strict GAAP",
                        ],
                    }
                ]
            },
        },
    ]
    create_payload = {
        "chat_id": chat_id,
        "title": "E2E Async User Message Steer",
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
def test_async_user_message_card_and_hermes_fallback_e2e() -> None:
    """Verify AsyncAgentMessageCard DOM rendering and turn-completed draft fallback (Hermes #64578)."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    chat_id = _seed_async_user_message_fixture(api_url)
    target_url = f"{ui_url}/{chat_id}"

    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")

    attach_chat_js = (
        "(async () => {\n"
        "  const bridge = window.__MYRM_E2E_CHAT__;\n"
        "  if (!bridge?.attachToChat) return { ok: false, err: 'no-bridge' };\n"
        f"  await bridge.attachToChat({json.dumps(chat_id)});\n"
        "  return { ok: true };\n"
        "})()"
    )

    with open_mcp_page(target_url, timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        wait_for_react_e2e_bridge(client, page, timeout_sec=60.0, page_url=target_url)

        attach_res = client.evaluate(page, attach_chat_js, timeout_sec=45.0)
        assert isinstance(attach_res, dict) and attach_res.get("ok") is True, f"Attach chat failed: {attach_res}"

        # 1. Verify Card DOM rendering in real Chrome
        card_state = wait_for_state(client, page, _CARD_RENDER_READY_JS, timeout_sec=20.0)
        assert card_state.get("ready") is True, f"Async card not rendered: {card_state}"

        # 2. Click Adopt/Option button and verify Hermes fallback to input message
        click_res = client.evaluate(page, _CLICK_ADOPT_BUTTON_JS, timeout_sec=10.0)
        assert isinstance(click_res, dict) and click_res.get("ok") is True, click_res

        # 3. Verify textarea has been populated with recommended text
        input_state = wait_for_state(client, page, _CHECK_INPUT_FALLBACK_JS, timeout_sec=15.0)
        assert input_state.get("ready") is True, f"Input draft not populated: {input_state}"


def _seed_multi_category_fixture(api_base: str) -> str:
    """Seed a conversation with progress, milestone, and question cards."""
    chat_id = f"e2emulti_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).replace(microsecond=0)
    messages = [
        {
            "messageId": f"msg-user-{chat_id}",
            "chatId": chat_id,
            "role": "user",
            "content": "Execute deep financial audit across multi-stage pipeline.",
            "createdAt": now.isoformat(),
        },
        {
            "messageId": f"msg-asst-{chat_id}",
            "chatId": chat_id,
            "role": "assistant",
            "content": "Starting deep audit workflow...",
            "createdAt": (now + timedelta(seconds=1)).isoformat(),
            "metadata": {
                "asyncUserMessages": [
                    {
                        "callId": "call_p1_progress",
                        "message": "Phase 1: Downloading 10-K financial reports (45% completed)",
                        "category": "progress",
                        "status": "pending",
                    },
                    {
                        "callId": "call_m1_milestone",
                        "message": "Milestone: Extracted GAAP balance sheet summary",
                        "category": "milestone",
                        "status": "pending",
                    },
                    {
                        "callId": "call_q1_pills",
                        "message": "Select fiscal year target for comparative ratios",
                        "category": "question",
                        "status": "pending",
                        "suggestedReplies": [
                            "FY2025 Standard",
                            "FY2024 Retrospective",
                        ],
                        "suggested_replies": [
                            "FY2025 Standard",
                            "FY2024 Retrospective",
                        ],
                    },
                ]
            },
        },
    ]
    create_payload = {
        "chat_id": chat_id,
        "title": "E2E Multi Category Steer",
        "action_mode": "agent",
        "is_incognito": False,
        "messages": messages,
    }
    http_json("POST", f"{api_base}/api/v1/chats/", body=create_payload)
    return chat_id


_MULTI_CARD_RENDER_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasProg = text.includes('Phase 1: Downloading 10-K');
  const hasMile = text.includes('Milestone: Extracted GAAP');
  const hasQues = text.includes('Select fiscal year target');
  const hasPill = text.includes('FY2025 Standard');
  return {
    ready: hasProg && hasMile && hasQues && hasPill,
    hasProg,
    hasMile,
    hasQues,
    hasPill,
  };
})()"""

_CLICK_PILL_BUTTON_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const pillBtn = buttons.find(b => (b.textContent || '').includes('FY2025 Standard'));
  if (!pillBtn) return { ok: false, err: 'pill-button-not-found' };
  pillBtn.click();
  return { ok: true, text: pillBtn.textContent };
})()"""

_CHECK_PILL_INPUT_FALLBACK_JS = """(() => {
  const inputEl = document.querySelector('[data-chat-input]');
  if (!inputEl) return { ready: false, err: 'no-input' };
  const val = inputEl.value || '';
  return {
    ready: val.includes('FY2025 Standard'),
    value: val,
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_multi_category_async_cards_and_suggested_pills_e2e() -> None:
    """Verify Progress, Milestone, and Question cards render together and pill click triggers fallback."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    chat_id = _seed_multi_category_fixture(api_url)
    target_url = f"{ui_url}/{chat_id}"

    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")

    attach_chat_js = (
        "(async () => {\n"
        "  const bridge = window.__MYRM_E2E_CHAT__;\n"
        "  if (!bridge?.attachToChat) return { ok: false, err: 'no-bridge' };\n"
        f"  await bridge.attachToChat({json.dumps(chat_id)});\n"
        "  return { ok: true };\n"
        "})()"
    )

    with open_mcp_page(target_url, timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        wait_for_react_e2e_bridge(client, page, timeout_sec=60.0, page_url=target_url)

        attach_res = client.evaluate(page, attach_chat_js, timeout_sec=45.0)
        assert isinstance(attach_res, dict) and attach_res.get("ok") is True, f"Attach chat failed: {attach_res}"

        # 1. Verify all 3 cards (Progress, Milestone, Question with pills) render in real Chrome
        multi_state = wait_for_state(client, page, _MULTI_CARD_RENDER_READY_JS, timeout_sec=20.0)
        assert multi_state.get("ready") is True, f"Multi cards not rendered: {multi_state}"

        # 2. Click suggested reply pill button
        click_res = client.evaluate(page, _CLICK_PILL_BUTTON_JS, timeout_sec=10.0)
        assert isinstance(click_res, dict) and click_res.get("ok") is True, click_res

        # 3. Verify textarea has been populated with pill text
        input_state = wait_for_state(client, page, _CHECK_PILL_INPUT_FALLBACK_JS, timeout_sec=15.0)
        assert input_state.get("ready") is True, f"Pill input fallback not populated: {input_state}"
