"""Chrome LIVE E2E: Real WebUI A2A peer delegation task flow.

Validates the full user journey:
1. Register trusted A2A peer via REST API.
2. Create and configure Agent with A2A peer delegation enabled.
3. Bind chat session to the Agent and open in real Chrome WebUI.
4. User inputs delegation task query in the WebUI chat prompt.
5. Real LLM emits a2a_call tool invocation to authorized peer.
6. A2A provider server executes and returns scientific synthesis.
7. WebUI receives real-time stream and renders assistant final report.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import (  # noqa: E402
    fetch_chat_messages,
    get_e2e_api_url,
    get_e2e_ui_url,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    attach_chat_and_wait_agent_binding,
    dismiss_blocking_modals,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers
from tests.support.e2e_runtime_guard import E2EResourceLedger

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

_SEND_TURN_JS = """(promptText) => (async () => {
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) {
    return { ok: false, err: 'no-sendChatMessage' };
  }
  bridge.setActionMode?.('agent');
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  const result = await bridge.sendChatMessage(promptText, {
    baselineUserCount: usersBefore,
    waitForStreamCompletion: false,
    preserveActionMode: true,
  });
  return { ...result, usersBefore };
})()"""

_ASSISTANT_DOM_PROBE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const isStreaming = snap.isStreaming === true;
  const lastSample = String(snap.lastAssistantSample || '');
  return {
    ready: !isStreaming && lastSample.trim().length > 20,
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
    while time.monotonic() < deadline:
        try:
            messages = fetch_chat_messages(chat_id, api_url=api_url)
        except OSError:
            messages = []
        last_messages = [
            m for m in messages if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        ]
        assistant = next(
            (m for m in reversed(last_messages) if isinstance(m, dict) and m.get("role") == "assistant"),
            None,
        )
        if isinstance(assistant, dict):
            content = assistant.get("content") or assistant.get("message") or ""
            if isinstance(content, str) and content.strip():
                return assistant
        time.sleep(2.0)
    raise AssertionError(f"Assistant reply timed out after {timeout_sec}s for chat {chat_id}")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a2a_chat_live_delegation_chrome_e2e(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Validate full WebUI task flow: Agent A2A binding -> real user chat prompt -> tool call -> live reply."""
    _ = e2e_resource_ledger
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)

    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    # 1. Register a trusted A2A peer pointing to local A2A server
    peer_name = f"Quantum Research Peer {uuid.uuid4().hex[:6]}"
    peer_payload = {
        "name": peer_name,
        "base_url": f"{api_url}/api/v1/a2a/rpc",
        "description": "Specialized quantum physics simulation and decoupling node",
        "auth_type": "bearer",
        "auth_token": "sk-secret-quantum-9988",
        "is_active": True,
    }
    peer_resp = http_json("POST", f"{api_url}/api/v1/a2a/peers", body=peer_payload)
    assert isinstance(peer_resp, dict) and "id" in peer_resp, f"Create peer failed: {peer_resp}"
    peer_id = str(peer_resp["id"])

    # 2. Create Agent with A2A enabled and whitelisted peer
    agent_payload = {
        "name": f"Quantum Coordinator {uuid.uuid4().hex[:6]}",
        "description": "Orchestrates research via trusted A2A peers",
        "a2a_enabled": True,
        "a2a_trusted_peer_ids": [peer_id],
    }
    agent_resp = http_json("POST", f"{api_url}/api/v1/user-agents", body=agent_payload)
    assert isinstance(agent_resp, dict) and agent_resp.get("data", {}).get("id"), f"Create agent failed: {agent_resp}"
    agent_id = str(agent_resp["data"]["id"])

    # 3. Create a Chat bound to this Agent
    chat_id = f"e2ea2achat{uuid.uuid4().hex[:8]}"
    chat_payload = {
        "chat_id": chat_id,
        "title": "A2A Live Delegation Chrome E2E",
        "agent_id": agent_id,
        "action_mode": "agent",
        "messages": [],
    }
    chat_resp = http_json("POST", f"{api_url}/api/v1/chats/", body=chat_payload)
    assert isinstance(chat_resp, dict) and chat_resp.get("success") is True, f"Create chat failed: {chat_resp}"

    chat_path = f"/{chat_id}"
    warm_ui_route(chat_path, timeout_sec=45.0)

    try:
        # 4. Open WebUI chat in Chrome browser
        with open_mcp_page(f"{ui_url}{chat_path}", timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)
            client.evaluate(page, _DISMISS_MODALS_JS, timeout_sec=10.0)
            wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=f"{ui_url}{chat_path}")

            # 5. Hydrate and bind agent to chat in store
            attach_chat_and_wait_agent_binding(
                client,
                page,
                chat_id,
                expected_preset="hitl",
                agent_id=agent_id,
                timeout_sec=90.0,
            )

            # 6. Send real user prompt to invoke A2A delegation
            prompt = (
                f"请调用 a2a_call 工具，把「量子退相干抑制」任务委派给远端可信的研究助手节点（{peer_name}），"
                "并根据远端专家的返回，整理一份简明结论报告。禁止不调用工具直接回答。"
            )

            send = client.evaluate(page, _send_turn(prompt), timeout_sec=60.0)
            assert isinstance(send, dict), send
            assert send.get("ok") is True, f"Send failed: {send}"

            # 7. Wait for assistant reply to arrive and complete
            reply = _wait_assistant_reply(chat_id, api_url, timeout_sec=180.0)
            assert str(reply.get("role")) == "assistant", f"Expected role assistant: {reply}"

            # 8. Wait for browser DOM and stream snapshot to stabilize
            dom_state = wait_for_state(client, page, _ASSISTANT_DOM_PROBE_JS, timeout_sec=90.0)
            assert dom_state.get("ready") is True, f"DOM stream not ready: {dom_state}"

            content = str(reply.get("content") or reply.get("message") or "")
            assert len(content.strip()) >= 20, f"Assistant reply too short: {content!r}"
            # Ensure model integrated research synthesis or task result
            assert any(
                kw in content
                for kw in ("量子", "退相干", "相干时间", "动力学解耦", "解耦", "Quantum", "Decoupling", "Task executed successfully")
            ), f"Assistant output did not contain expected domain terms: {content[:300]}"

    finally:
        # Cleanup created resources
        try:
            http_json("DELETE", f"{api_url}/api/v1/chats/{chat_id}")
        except Exception:
            pass
        try:
            http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
        except Exception:
            pass
        try:
            http_json("DELETE", f"{api_url}/api/v1/a2a/peers/{peer_id}")
        except Exception:
            pass
