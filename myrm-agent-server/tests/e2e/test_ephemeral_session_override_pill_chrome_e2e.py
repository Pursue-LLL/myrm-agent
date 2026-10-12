"""Chrome E2E: memory tool write → same-chat ephemeral override pill (Item 98).

Proves the live chain: durable memory write → record_ephemeral_memory_delta →
SSE memory_brief_status.session_ephemeral_delta_count → Memory Insight pill.
Real Chrome, real backend, real LLM; no mocks.
"""

from __future__ import annotations

import json
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
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
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
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402

_PILL_TEXT_EN = "Updated in this chat"


def _write_prompt(suffix: str) -> str:
    token = f"EphemeralE2E-{suffix}"
    return (
        "You must call the semantic memory save/update tool before your reply. "
        f"Persist this exact fact: my preferred display name is {token}. "
        "After the tool call succeeds, reply with only: SAVED_OK"
    )


def _send_turn_js(prompt: str) -> str:
    prompt_json = json.dumps(prompt)
    return f"""(async () => {{
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return {{ ok: false, err: 'no-sendChatMessage' }};
  bridge.setActionMode?.('agent');
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  const result = await bridge.sendChatMessage({prompt_json}, {{
    baselineUserCount: usersBefore,
    preserveActionMode: true,
  }});
  return {{ ...result, usersBefore }};
}})()"""


def _create_agent(api_url: str, name: str) -> str:
    agent_resp = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={"name": name, "description": "Ephemeral session override pill e2e"},
    )
    assert isinstance(agent_resp, dict) and agent_resp.get("data", {}).get("id"), agent_resp
    return str(agent_resp["data"]["id"])


def _create_chat(api_url: str, chat_id: str, title: str, agent_id: str) -> None:
    chat_resp = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": title,
            "agent_id": agent_id,
            "action_mode": "agent",
            "messages": [],
        },
    )
    assert isinstance(chat_resp, dict) and chat_resp.get("success") is True, chat_resp


_ATTACH_CHAT_PROBE = """(() => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  const store = window.__myrmChatStore?.getState?.();
  const attached =
    store?.chatId === {chat_id_json}
    && Boolean(store?.isMessagesLoaded)
    && !Boolean(store?.loadError)
    && !Boolean(store?.notFound);
  if (attached) return {{ ready: true, chatId: store?.chatId ?? null }};
  if (bridge?.attachToChat && !window.__MYRM_E2E_ATTACHING__) {{
    window.__MYRM_E2E_ATTACHING__ = true;
    bridge.attachToChat({chat_id_json}).catch(() => {{}}).finally(() => {{
      window.__MYRM_E2E_ATTACHING__ = false;
    }});
  }}
  return {{
    ready: false,
    chatId: store?.chatId ?? null,
    isMessagesLoaded: Boolean(store?.isMessagesLoaded),
    loading: Boolean(store?.loading),
    loadError: Boolean(store?.loadError),
    notFound: Boolean(store?.notFound),
    err: !bridge ? 'no-bridge' : null,
  }};
}})()"""


def _session_override_probe_js() -> str:
    return """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = Array.isArray(store?.messages) ? store.messages : [];
  const assistants = msgs.filter((m) => m?.role === 'assistant');
  const last = assistants.length ? assistants[assistants.length - 1] : null;
  const count = last?.memoryBriefStatus?.session_ephemeral_delta_count ?? 0;
  const bodyText = document.body?.innerText ?? '';
  const pillVisible = bodyText.includes('Updated in this chat');
  return {
    ok: count > 0 || pillVisible,
    count,
    pillVisible,
    assistantCount: assistants.length,
    hasBrief: Boolean(last?.memoryBriefStatus),
  };
})()"""


def _attach_probe_js(chat_id: str) -> str:
    return _ATTACH_CHAT_PROBE.format(chat_id_json=json.dumps(chat_id))


def _wait_assistant_reply(chat_id: str, api_url: str, *, timeout_sec: float = 240.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        messages = fetch_chat_messages(chat_id, api_url=api_url)
        assistant = next(
            (m for m in reversed(messages) if isinstance(m, dict) and m.get("role") == "assistant"),
            None,
        )
        if isinstance(assistant, dict):
            content = assistant.get("content") or assistant.get("message") or ""
            if isinstance(content, str) and content.strip():
                return assistant
        time.sleep(2.0)
    pytest.fail(f"assistant reply not received within {timeout_sec}s for chat {chat_id}")


def _wait_active_ephemeral_deltas(api_url: str, chat_id: str, *, timeout_sec: float = 120.0) -> list[object]:
    deadline = time.monotonic() + timeout_sec
    last: list[object] = []
    while time.monotonic() < deadline:
        try:
            payload = http_json("GET", f"{api_url}/api/memory/ephemeral-delta/active/{chat_id}")
            if isinstance(payload, list) and payload:
                return payload
            last = payload if isinstance(payload, list) else []
        except (RuntimeError, OSError, ValueError):
            pass
        time.sleep(2.0)
    pytest.fail(
        f"no active ephemeral deltas for chat {chat_id} after {timeout_sec}s; last={json.dumps(last)[:200]}"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_ephemeral_session_override_pill_after_memory_write_live() -> None:
    """Memory tool write in one chat must surface the session-override pill in WebUI."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    suffix = uuid.uuid4().hex[:8]
    agent_id = _create_agent(api_url, f"Ephemeral Pill Probe {suffix}")
    chat_id = f"e2ephemeral{suffix}"
    _create_chat(api_url, chat_id, "Ephemeral Session Override E2E", agent_id)

    chat_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=chat_url)
        bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
        assert bridge.get("ready") is True, bridge

        attached = wait_for_state(
            client,
            page,
            _attach_probe_js(chat_id),
            timeout_sec=90.0,
            page_url=chat_url,
        )
        assert attached.get("ready") is True, attached

        sent = client.evaluate(page, _send_turn_js(_write_prompt(suffix)), timeout_sec=120.0)
        assert isinstance(sent, dict) and sent.get("ok") is True, sent

    _wait_assistant_reply(chat_id, api_url, timeout_sec=240.0)
    _wait_active_ephemeral_deltas(api_url, chat_id, timeout_sec=120.0)

    with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=chat_url)
        bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
        assert bridge.get("ready") is True, bridge
        attached = wait_for_state(
            client,
            page,
            _attach_probe_js(chat_id),
            timeout_sec=90.0,
            page_url=chat_url,
        )
        assert attached.get("ready") is True, attached

        probe = wait_for_state(
            client,
            page,
            _session_override_probe_js(),
            timeout_sec=90.0,
            page_url=chat_url,
        )
        assert probe.get("ok") is True, json.dumps(probe, ensure_ascii=False)
        assert int(probe.get("count") or 0) > 0 or probe.get("pillVisible") is True
        if probe.get("pillVisible") is not True:
            body_snip = client.evaluate(
                page,
                "(() => document.body?.innerText?.slice(0, 800) ?? '')()",
                timeout_sec=15.0,
            )
            pytest.fail(
                f"expected pill text {_PILL_TEXT_EN!r}; probe={probe}; body={body_snip!r}"
            )
