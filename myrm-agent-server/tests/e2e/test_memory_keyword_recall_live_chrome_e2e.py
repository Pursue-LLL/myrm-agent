"""Chrome E2E: cross-chat keyword memory recall over the BM25 sparse channel.

Real business task flow for the persistent BM25 sparse recall path
(`toolkits/memory/_internal/bm25_sparse_index.py` + qdrant sparse mixin):
a distinctive fact (project codename + package manager) is written in one
chat, then a keyword-only question is asked in a *second* chat with zero
shared conversation context. The final reply must surface both exact
keywords — they can only arrive through the memory system's keyword
recall (the BM25 channel serves proper-noun/keyword matching), proving
the end-to-end write → persist → sparse-index → recall → reply chain on
the real WebUI with a real model. No mocks: real Chrome, real backend,
real LLM, real vector store.
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

# Distinctive keywords: latin tokens only the memory recall path can surface —
# a context-free chat has zero conversation state to fabricate "Kestrel-77" from.
_WRITE_PROMPT = "请记住:我的内部项目代号是 Kestrel-77,部署时只用 uv 管理依赖,不用 pip。"
_RECALL_PROMPT = "我的内部项目代号是什么?我部署时用什么包管理器?"


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
    waitForStreamCompletion: false,
    preserveActionMode: true,
  }});
  return {{ ...result, usersBefore }};
}})()"""


def _create_agent(api_url: str, name: str) -> str:
    agent_resp = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={"name": name, "description": "Memory keyword recall e2e probe agent"},
    )
    assert isinstance(agent_resp, dict) and agent_resp.get("data", {}).get("id"), f"Create agent failed: {agent_resp}"
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
    assert isinstance(chat_resp, dict) and chat_resp.get("success") is True, f"Create chat failed: {chat_resp}"


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


def _attach_probe_js(chat_id: str) -> str:
    return _ATTACH_CHAT_PROBE.format(chat_id_json=json.dumps(chat_id))


def _open_chat_and_send(
    ui_url: str,
    chat_id: str,
    prompt: str,
) -> dict[str, object]:
    """Open a chat page in real Chrome, wait for store attach, send one real turn.

    The send gate requires the hydrated chat (chatId + isMessagesLoaded):
    sendMessage on an unattached store silently no-ops with a toast, so the
    attach wait below is what keeps the turn from racing route hydration.
    """
    chat_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=chat_url)
        bridge = wait_for_react_e2e_bridge(
            client,
            page,
            timeout_sec=90.0,
            page_url=chat_url,
        )
        assert bridge.get("ready") is True, json.dumps(bridge, ensure_ascii=False)

        attached = wait_for_state(
            client,
            page,
            _attach_probe_js(chat_id),
            timeout_sec=90.0,
            page_url=chat_url,
        )
        assert attached.get("ready") is True, json.dumps(attached, ensure_ascii=False)

        sent = client.evaluate(
            page,
            _send_turn_js(prompt),
            timeout_sec=90.0,
        )
        assert isinstance(sent, dict) and sent.get("ok") is True, (
            f"send turn failed for chat {chat_id}: {json.dumps(sent, ensure_ascii=False)[:600]}"
        )
        return sent


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
        last_messages = [m for m in messages if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
        assistant = next(
            (m for m in reversed(last_messages) if isinstance(m, dict) and m.get("role") == "assistant"),
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


def _await_memory_write_ledger(api_url: str, chat_id: str, *, timeout_sec: float = 120.0) -> None:
    """Wait until the write-side extraction lands in the session memory ledger.

    Memory extraction runs asynchronously after the assistant reply; the
    session trace endpoint exposes the memory operation ledger, so polling it
    until the first event lands keeps the recall turn from racing the write.
    """
    deadline = time.monotonic() + timeout_sec
    last: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        try:
            payload = http_json("GET", f"{api_url}/api/v1/statistics/session/{chat_id}/trace")
            data = payload.get("data") if isinstance(payload, dict) else None
            events = data.get("memory_events") if isinstance(data, dict) else None
            if isinstance(events, list) and events:
                return
            last = events if isinstance(events, list) else []
        except (RuntimeError, OSError, ValueError):
            pass
        time.sleep(2.0)
    pytest.fail(
        f"memory write ledger empty for chat {chat_id} after {timeout_sec}s; "
        f"last_events={json.dumps(last, ensure_ascii=False)[:300]}"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_keyword_recall_cross_chat_live() -> None:
    """Write a fact in chat A, ask keyword-only in fresh chat B, recall must hit."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    suffix = uuid.uuid4().hex[:8]
    agent_id = _create_agent(api_url, f"Memory Recall Probe {suffix}")
    chat_one = f"e2ekwrecall{suffix}a"
    chat_two = f"e2ekwrecall{suffix}b"
    _create_chat(api_url, chat_one, "Memory Keyword Recall Write E2E", agent_id)
    _create_chat(api_url, chat_two, "Memory Keyword Recall Ask E2E", agent_id)

    # ── Turn 1: write the distinctive fact (real model, real extraction) ──
    _open_chat_and_send(ui_url, chat_one, _WRITE_PROMPT)
    _wait_assistant_reply(chat_one, api_url, timeout_sec=180.0)
    _await_memory_write_ledger(api_url, chat_one, timeout_sec=120.0)

    # ── Turn 2: context-free chat, keyword-only recall ──
    _open_chat_and_send(ui_url, chat_two, _RECALL_PROMPT)
    reply = _wait_assistant_reply(chat_two, api_url, timeout_sec=180.0)

    text = str(reply.get("content") or reply.get("message") or "")
    lowered = text.lower()
    # The codename only exists in the memory persisted from chat one; a
    # context-free chat can only surface it through keyword recall.
    assert "kestrel" in lowered, f"codename keyword missing from recall reply: {text[:400]}"
    assert "uv" in lowered, f"package-manager keyword missing from recall reply: {text[:400]}"


# CJK keywords: the recall reply must surface Chinese tokens that only exist
# in the persisted memory — proves the jieba tokenization chain (BM25 sparse
# channel) serves CJK segments, the dominant locale for real users.
_WRITE_PROMPT_CJK = "请记住:我家的猫叫雪球,今年三岁,最爱吃冻干鸡肉零食。"
_RECALL_PROMPT_CJK = "我家的猫叫什么名字?它最爱吃什么零食?"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_keyword_recall_cross_chat_cjk_live() -> None:
    """Write a CJK fact in chat A, ask keyword-only in fresh chat B, recall must hit."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    suffix = uuid.uuid4().hex[:8]
    agent_id = _create_agent(api_url, f"Memory Recall CJK Probe {suffix}")
    chat_one = f"e2ekwrecall{suffix}c"
    chat_two = f"e2ekwrecall{suffix}d"
    _create_chat(api_url, chat_one, "Memory CJK Recall Write E2E", agent_id)
    _create_chat(api_url, chat_two, "Memory CJK Recall Ask E2E", agent_id)

    # ── Turn 1: write the distinctive CJK fact (real model, real extraction) ──
    _open_chat_and_send(ui_url, chat_one, _WRITE_PROMPT_CJK)
    _wait_assistant_reply(chat_one, api_url, timeout_sec=180.0)
    _await_memory_write_ledger(api_url, chat_one, timeout_sec=120.0)

    # ── Turn 2: context-free chat, CJK keyword-only recall ──
    _open_chat_and_send(ui_url, chat_two, _RECALL_PROMPT_CJK)
    reply = _wait_assistant_reply(chat_two, api_url, timeout_sec=180.0)

    text = str(reply.get("content") or reply.get("message") or "")
    # "雪球" and "冻干" only exist in the memory persisted from chat one; a
    # context-free chat can only surface them through CJK keyword recall.
    assert "雪球" in text, f"CJK cat-name keyword missing from recall reply: {text[:400]}"
    assert "冻干" in text, f"CJK snack keyword missing from recall reply: {text[:400]}"
