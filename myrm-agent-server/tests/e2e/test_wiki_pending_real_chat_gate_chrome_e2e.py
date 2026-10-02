"""Real Chrome E2E: real-LLM chat draft lands in the pending panel, then UI reject.

Full real-business-task loop over the publication gate and the pending-review
panel with no mock on the critical path: a real agent chat turn (real model,
real wiki tool call) is intercepted by the fail-closed publication gate and
lands as a staged-for-review draft; the draft then surfaces in the real
Settings wiki panel and a real UI reject action removes it with the stats
badge synced. PRIVATE candidate database keeps the shared stack untouched:

  create wiki-enabled agent + chat -> real turn (model calls the wiki tool,
  gate blocks the publish, model replies with the staged result) ->
  REST pending poll until the unique concept appears -> open the real panel
  (settled probe: concept row + reject control + badge = base+1) ->
  click the row reject button -> concept row disappears, badge back to base.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import fetch_chat_messages, wait_e2e_provider_ready  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    open_wiki_settings_mcp_page,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_react_e2e_bridge,
    wait_for_state,
    wait_for_wiki_settings_shell,
    warm_ui_route,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402

_PANEL_PATH = "/settings/wiki?wikiTab=pendingEdits"
_PANEL_WAIT_SEC = 90.0
_SHELL_WAIT_SEC = 45.0
_MAX_ATTEMPTS = 2

_SEND_TURN_JS = """(async () => {{
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
  return {{ ready: false, chatId: store?.chatId ?? null, err: !bridge ? 'no-bridge' : null }};
}})()"""

_INSTALL_ERROR_HOOKS_JS = """(() => {
  window.__e2eErrors = [];
  window.onerror = (msg, src, line, col, errObj) => {
    window.__e2eErrors.push(
      `error: ${msg} @ ${src}:${line}`
      + (errObj && errObj.stack ? ` | ${errObj.stack.split('\\n').slice(0, 3).join(' <- ')}` : ''),
    );
    return false;
  };
  window.addEventListener('unhandledrejection', (e) => {
    const r = (e && e.reason) || {};
    window.__e2eErrors.push(`rejection: ${r.stack || String(r)}`);
  });
  return true;
})()"""

_SKIP_DEFERRED_LOCALE_JS = """(() => {
  try {
    sessionStorage.setItem('e2e_skip_deferred_locale', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_PANEL_CONCEPT_PROBE = """(() => {{
  const list = document.querySelector('[data-testid="pending-edits-list"]');
  const text = list ? list.textContent : '';
  const badge = document.querySelector('[data-testid="pending-stats-badge"]');
  const badgeNum = badge ? ((badge.textContent.match(/\\d+/) || [''])[0]) : '';
  const rejectBtn = document.querySelector('[data-testid="pending-reject-button"]');
  return {{
    ready: !!list && text.includes({concept_json}) && !!rejectBtn && badgeNum === {badge_json},
    conceptVisible: text.includes({concept_json}),
    items: list ? list.children.length : 0,
    badgeNum,
    hasReject: !!rejectBtn,
    errors: (window.__e2eErrors || []).slice(-6),
    href: location.href,
  }};
}})()"""

_PANEL_REJECTED_PROBE = """(() => {{
  const list = document.querySelector('[data-testid="pending-edits-list"]');
  const text = list ? list.textContent : '';
  const badge = document.querySelector('[data-testid="pending-stats-badge"]');
  const badgeNum = badge ? ((badge.textContent.match(/\\d+/) || [''])[0]) : '';
  return {{
    ready: !!list && !text.includes({concept_json}) && badgeNum === {badge_json},
    conceptVisible: text.includes({concept_json}),
    items: list ? list.children.length : 0,
    badgeNum,
    errors: (window.__e2eErrors || []).slice(-6),
    href: location.href,
  }};
}})()"""

_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "MUX",
    "CDP",
    "Runtime.evaluate",
    "Page.navigate",
    "connection reset",
    "Page shell did not hydrate",
    "transport dead",
    "transport unavailable",
    "recover_mux",
    "chrome-error",
    "lease not found",
    "wave is not open",
    "No target with given id",
    "Session with given id not found",
    "did not become ready",
    "E2E_ROUTE_HYDRATION_TIMEOUT",
)


def _panel_concept_probe(concept: str, expected_badge: str) -> str:
    return _PANEL_CONCEPT_PROBE.format(concept_json=json.dumps(concept), badge_json=json.dumps(expected_badge))


def _panel_rejected_probe(concept: str, expected_badge: str) -> str:
    return _PANEL_REJECTED_PROBE.format(concept_json=json.dumps(concept), badge_json=json.dumps(expected_badge))


def _create_wiki_agent(api_url: str, name: str) -> str:
    """Agent with the wiki builtin tool enabled (default profile excludes it)."""
    agent_resp = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": name,
            "description": "Wiki pending gate e2e probe agent",
            "enabled_builtin_tools": ["wiki", "web_search", "memory"],
        },
    )
    assert isinstance(agent_resp, dict) and agent_resp.get("data", {}).get("id"), (
        f"Create wiki agent failed: {agent_resp}"
    )
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
    assert isinstance(chat_resp, dict) and chat_resp.get("success") is True, (
        f"Create chat failed: {chat_resp}"
    )


def _open_chat_and_send(ui_url: str, chat_id: str, prompt: str) -> dict[str, object]:
    """Open the chat page in real Chrome, wait for attach, send one real turn."""
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
            _ATTACH_CHAT_PROBE.format(chat_id_json=json.dumps(chat_id)),
            timeout_sec=90.0,
            page_url=chat_url,
        )
        assert attached.get("ready") is True, json.dumps(attached, ensure_ascii=False)
        sent = client.evaluate(page, _SEND_TURN_JS.format(prompt_json=json.dumps(prompt)), timeout_sec=90.0)
        assert isinstance(sent, dict) and sent.get("ok") is True, (
            f"send turn failed for chat {chat_id}: {json.dumps(sent, ensure_ascii=False)[:600]}"
        )
        return sent


def _wait_assistant_reply(chat_id: str, api_url: str, *, timeout_sec: float = 180.0) -> str:
    """Poll the real chat messages until the model's final reply lands."""
    deadline = time.monotonic() + timeout_sec
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
            content = str(assistant.get("content") or assistant.get("message") or "")
            if content.strip():
                return content
        time.sleep(3.0)
    pytest.fail(f"assistant reply empty for chat {chat_id} after {timeout_sec}s")


def _wait_pending_concept(
    api_url: str,
    concept: str,
    *,
    timeout_sec: float = 90.0,
) -> dict[str, object]:
    """Poll the pending list until the gate-staged concept shows up."""
    deadline = time.monotonic() + timeout_sec
    last: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        body = http_json("GET", f"{api_url}/api/v1/wiki/pending?limit=50")
        assert isinstance(body, dict)
        edits = body.get("pending_edits")
        if isinstance(edits, list):
            last = [e for e in edits if isinstance(e, dict)]
            hit = next((e for e in last if str(e.get("concept_name", "")) == concept), None)
            if isinstance(hit, dict):
                return hit
        time.sleep(2.0)
    pytest.fail(
        f"concept {concept} never landed in the pending list after {timeout_sec}s; "
        f"last_head={[str(e.get('concept_name')) for e in last[:5]]}"
    )


def _is_transport_retryable(exc: BaseException) -> bool:
    return any(marker in str(exc) for marker in _TRANSPORT_RETRY_MARKERS)


def _run_real_chat_gate_flow(api_url: str, ui_url: str) -> None:
    base_stats = http_json("GET", f"{api_url}/api/v1/wiki/pending?limit=1")["stats"]
    assert isinstance(base_stats, dict)
    base_pending = int(base_stats["pending"])

    suffix = uuid.uuid4().hex[:8]
    concept = f"E2E-Real-Gate-{suffix}"
    agent_id = _create_wiki_agent(api_url, f"Wiki Gate Probe {suffix}")
    chat_id = f"e2ewikigate{suffix}"
    _create_chat(api_url, chat_id, "Wiki Pending Gate E2E", agent_id)

    # ── Real model turn: the agent must call the wiki tool; the fail-closed
    # gate blocks the publish and stages the draft for review. ──
    prompt = (
        f"请使用 wiki 写入工具，把下面这条知识保存到我的个人 wiki："
        f"概念名「{concept}」，"
        f"内容「E2E 真实链路验证条目：这条知识由真实模型会话通过 wiki 工具写入，"
        f"用于验证待审拦截与面板审批闭环。」请直接调用工具写入。"
    )
    _open_chat_and_send(ui_url, chat_id, prompt)
    reply = _wait_assistant_reply(chat_id, api_url, timeout_sec=180.0)
    # Keep the real model's answer on record (-s) — evidence of the live turn.
    print(f"[real-model reply] {reply[:240]}")

    # ── Gate interception: the unique concept must land in the pending list. ──
    staged = _wait_pending_concept(api_url, concept, timeout_sec=90.0)
    edit_id = staged.get("id")
    assert isinstance(edit_id, int), staged

    # ── Real panel: the staged draft must be visible with the badge at base+1. ──
    panel_url = f"{ui_url.rstrip('/')}{_PANEL_PATH}"
    with open_wiki_settings_mcp_page(panel_url, timeout_ms=120_000, request_timeout_sec=180.0) as (client, page):
        client.evaluate(page, _SKIP_DEFERRED_LOCALE_JS, timeout_sec=15.0)
        reload_mcp_page(
            client,
            page,
            target_url=panel_url,
            timeout_ms=90_000,
            ignore_cache=True,
        )
        client.evaluate(page, _INSTALL_ERROR_HOOKS_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page, recover_url=panel_url)
        shell = wait_for_wiki_settings_shell(
            client,
            page,
            page_url=panel_url,
            timeout_sec=_SHELL_WAIT_SEC,
        )
        assert shell.get("ready") is True, json.dumps(shell, indent=2, ensure_ascii=False)

        staged_probe = _panel_concept_probe(concept, str(base_pending + 1))
        staged_state = wait_for_state(client, page, staged_probe, timeout_sec=_PANEL_WAIT_SEC)
        assert staged_state.get("conceptVisible") is True, (
            f"gate-staged draft must surface in the panel: {json.dumps(staged_state, ensure_ascii=False)}"
        )
        assert staged_state.get("badgeNum") == str(base_pending + 1), staged_state
        assert staged_state.get("errors") == [], staged_state

        # ── Real UI reject: the row must disappear and the badge drop to base. ──
        clicked = client.evaluate(
            page,
            """(() => {
              const btn = document.querySelector('[data-testid="pending-reject-button"]');
              if (!btn) return false;
              btn.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert clicked is True, "reject button not found on the staged row"

        rejected_probe = _panel_rejected_probe(concept, str(base_pending))
        rejected_state = wait_for_state(client, page, rejected_probe, timeout_sec=_PANEL_WAIT_SEC)
        assert rejected_state.get("conceptVisible") is False, (
            f"rejected draft must leave the panel: {json.dumps(rejected_state, ensure_ascii=False)}"
        )
        assert rejected_state.get("badgeNum") == str(base_pending), rejected_state
        assert rejected_state.get("errors") == [], rejected_state

    # Authoritative REST check after the UI action (model reply kept for the report).
    final_stats = http_json("GET", f"{api_url}/api/v1/wiki/pending?limit=1")["stats"]
    assert isinstance(final_stats, dict)
    assert int(final_stats["pending"]) == base_pending, final_stats
    assert int(final_stats["rejected"]) == int(base_stats["rejected"]) + 1, final_stats


def _run_with_transport_retry(runner: Callable[[str, str], None], api_url: str, ui_url: str) -> None:
    last_error: BaseException | None = None
    for _attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            runner(api_url, ui_url)
            return
        except Exception as exc:
            last_error = exc
            if _attempt >= _MAX_ATTEMPTS or not _is_transport_retryable(exc):
                raise
    if last_error is not None:
        raise last_error


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_real_chat_draft_lands_in_pending_panel_and_ui_review() -> None:
    """Real model writes via the wiki tool, gate stages it, UI reject closes."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    warm_ui_route("/settings")
    warm_ui_route("/settings/wiki")
    _run_with_transport_retry(_run_real_chat_gate_flow, api_url, ui_url)
