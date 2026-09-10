"""End-to-End Universal Task Flow E2E: Risk Triggered MoA Advisor Stream Execution.

Validates the full business workflow:
1. Seed live LLM providers and assert provider readiness.
2. Create agent configured with moa_overlay fanout='risk_triggered' and auto_on_reasoning=True.
3. Create chat session bound to the agent.
4. Issue real task prompt through /api/v1/agents/agent-stream.
5. Live LLM execution with AdvisorRiskTriggerRouter middleware gate active.
6. Open real WebUI chat in Chrome browser via CDP, simulate real user typing prompt, and verify live streaming DOM reply.
"""

from __future__ import annotations

import json
import time
import uuid

import httpx
import pytest

from cdp_chat.support import (
    fetch_chat_messages,
    get_e2e_api_url,
    get_e2e_ui_url,
    wait_e2e_provider_ready,
)
from tests.support.chrome_mcp_e2e import (
    attach_chat_and_wait_agent_binding,
    dismiss_blocking_modals,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)
from tests.support.e2e_provider_seed import (
    build_e2e_model_selection,
    seed_live_e2e_providers,
)
from tests.support.subagent_hitl_stream import consume_agent_stream

_DISMISS_MODALS_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const dismissBtn = buttons.find((b) =>
    /Dismiss|Got it|Close|关闭|我知道了/i.test((b.textContent || '').trim()),
  );
  if (dismissBtn) {
    dismissBtn.click();
    return { ok: true, clicked: true };
  }
  return { ok: true, clicked: false };
})()"""

_ASSISTANT_DOM_PROBE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const isStreaming = snap.isStreaming === true;
  const lastSample = String(snap.lastAssistantSample || '');
  return {
    ready: !isStreaming && lastSample.trim().length > 10,
    isStreaming,
    lastSample: lastSample.slice(0, 500),
  };
})()"""


def _send_turn(prompt: str) -> str:
    prompt_json = json.dumps(prompt)
    return f"""(async () => {{
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return {{ ok: false, err: 'no-sendChatMessage' }};
  bridge.setActionMode?.('agent');
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  const result = await bridge.sendChatMessage({prompt_json}, {{
    baselineUserCount: usersBefore,
    waitForStreamCompletion: false,
    preserveActionMode: true,
  }});
  return {{ ...result, usersBefore }};
}})()"""


def _wait_assistant_reply(
    chat_id: str,
    api_url: str,
    *,
    timeout_sec: float = 180.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    last_messages: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        try:
            messages = fetch_chat_messages(chat_id, api_url=api_url)
        except OSError:
            messages = []
        last_messages = [
            m
            for m in messages
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        ]
        assistant = next(
            (
                m
                for m in reversed(last_messages)
                if isinstance(m, dict) and m.get("role") == "assistant"
            ),
            None,
        )
        if isinstance(assistant, dict):
            content = assistant.get("content") or assistant.get("message") or ""
            if isinstance(content, str) and content.strip():
                return assistant
        last = assistant or {}
        time.sleep(2.0)
    pytest.fail(
        f"assistant reply not received within {timeout_sec}s for chat {chat_id}; "
        f"last={json.dumps(last, ensure_ascii=False)[:300]} "
        f"messages={json.dumps(last_messages, ensure_ascii=False)[:800]}"
    )


def _delete_agent(api_url: str, agent_id: str) -> None:
    try:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
    except Exception:
        pass


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_moa_overlay_risk_triggered_live_task_flow_e2e() -> None:
    """Lane-C: Universal Task Flow E2E - Agent with risk_triggered MoA executes full task flow."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)

    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — verify .env.test LLM credentials")

    name = f"moa-flow-e2e-{uuid.uuid4().hex[:8]}"
    res = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": name,
            "system_prompt": "You are a concise technical architect assistant.",
            "engine_params": {
                "moa_overlay": {
                    "enabled": True,
                    "fanout": "risk_triggered",
                    "auto_on_reasoning": True,
                    "reference_model_selections": [
                        {"provider_id": "openai-like", "model": "gemini-3.8-flash-high"}
                    ],
                }
            },
        },
    )
    agent_id = (res.get("data") or {}).get("id")
    assert agent_id, f"failed to create agent for task flow: {res}"

    try:
        chat_id = f"chat-moa-{uuid.uuid4().hex[:8]}"
        chat_payload = {
            "chat_id": chat_id,
            "title": "MoA E2E",
            "agent_id": agent_id,
            "action_mode": "agent",
            "messages": [],
        }
        http_json("POST", f"{api_url}/api/v1/chats/", body=chat_payload)
        message_id = f"msg-{uuid.uuid4().hex[:8]}"
        payload = {
            "query": "请用简短一句话说明微服务架构相比单体架构的核心优势。",
            "chatId": chat_id,
            "messageId": message_id,
            "agentId": agent_id,
            "modelSelection": build_e2e_model_selection(use_lite=True),
            "actionMode": "general",
            "securityPreset": "explore",
        }

        with httpx.Client() as client:
            action_type, events, errors = consume_agent_stream(client, api_url, payload)

        assert len(errors) == 0, f"agent-stream returned errors: {errors}"
        event_types = [str(e.get("type")) for e in events]
        assert "message_end" in event_types, f"missing message_end in {event_types}"
        assert any(t in event_types for t in ("message", "content_delta")), f"missing message tokens in {event_types}"

        chunks = []
        for e in events:
            if e.get("type") in ("message", "content_delta"):
                data = e.get("data")
                if isinstance(data, dict):
                    chunks.append(str(data.get("delta") or data.get("content") or ""))
                elif isinstance(data, str):
                    chunks.append(data)
        full_reply = "".join(chunks)
        assert len(full_reply.strip()) > 5, f"Expected non-empty reply, got: {full_reply}"
    finally:
        _delete_agent(api_url, agent_id)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_moa_overlay_risk_triggered_webui_chat_dom_flow_e2e() -> None:
    """Lane-C / WebUI: End-to-end user journey in real Chrome WebUI with risk_triggered MoA Agent."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)

    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — verify .env.test LLM credentials")

    name = f"moa-webui-e2e-{uuid.uuid4().hex[:8]}"
    res = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": name,
            "system_prompt": "You are a concise technical architect assistant.",
            "engine_params": {
                "moa_overlay": {
                    "enabled": True,
                    "fanout": "risk_triggered",
                    "auto_on_reasoning": True,
                    "reference_model_selections": [
                        {"provider_id": "openai-like", "model": "gemini-3.8-flash-high"}
                    ],
                }
            },
        },
    )
    agent_id = (res.get("data") or {}).get("id")
    assert agent_id, f"failed to create agent for webui chat flow: {res}"

    chat_id = f"e2emoachat{uuid.uuid4().hex[:8]}"
    chat_payload = {
        "chat_id": chat_id,
        "title": "MoA WebUI Live Flow",
        "agent_id": agent_id,
        "action_mode": "agent",
        "messages": [],
    }
    chat_resp = http_json("POST", f"{api_url}/api/v1/chats/", body=chat_payload)
    assert isinstance(chat_resp, dict) and chat_resp.get("success") is True, f"Create chat failed: {chat_resp}"

    chat_path = f"/{chat_id}"
    warm_ui_route(chat_path, timeout_sec=45.0)

    try:
        with open_mcp_page(f"{ui_url}{chat_path}", timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)
            client.evaluate(page, _DISMISS_MODALS_JS, timeout_sec=10.0)
            wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=f"{ui_url}{chat_path}")

            attach_chat_and_wait_agent_binding(
                client,
                page,
                chat_id,
                expected_preset="hitl",
                agent_id=agent_id,
                timeout_sec=90.0,
            )

            prompt = "请用一句话说明微服务解耦对团队交付效率的影响。"
            send = client.evaluate(page, _send_turn(prompt), timeout_sec=60.0)
            assert isinstance(send, dict), send
            assert send.get("ok") is True, f"Send failed: {send}"

            reply = _wait_assistant_reply(chat_id, api_url, timeout_sec=180.0)
            assert str(reply.get("role")) == "assistant", f"Expected role assistant: {reply}"

            dom_state = wait_for_state(client, page, _ASSISTANT_DOM_PROBE_JS, timeout_sec=90.0)
            assert dom_state.get("ready") is True, f"DOM stream not ready: {dom_state}"

            content = str(reply.get("content") or reply.get("message") or "")
            assert len(content.strip()) >= 5, f"Assistant reply too short: {content!r}"
    finally:
        _delete_agent(api_url, agent_id)
