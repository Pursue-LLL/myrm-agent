"""Chrome LIVE_AGENT E2E: foreground bash spill → evicted API + LiveTerminal Drawer.

Phase 1: real Chrome UI sendChatMessage (LIVE path, same as deep search) with yolo
code_execute agent — poll API for bash_code_execute_tool + evicted_file_ref.

Phase 2: same tab — expand Task Steps, View Full Output, Drawer shows marker.
"""

from __future__ import annotations

import json
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    ensure_e2e_hitl_mode,
    fetch_chat_messages,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_MARKER = "UECD_BASH_FG_MARKER"
_BASH_TOOL = "bash_code_execute_tool"
_OUTPUT_BASENAME_RE = re.compile(r"^output_[a-f0-9]{8}\.txt$")
_PAGE_TIMEOUT_MS = 180_000
_MAX_UI_ATTEMPTS = 2
_API_POLL_TIMEOUT_SEC = 480.0
_SPILL_CHARS = 180_000

_FG_PROMPT = (
    "Run exactly one foreground shell command with bash_code_execute_tool "
    "(run_in_background must be false):\n"
    f'- command: python3 -c "print(\'{_MARKER}\'); print(\'x\' * {_SPILL_CHARS})"\n'
    "- run_in_background: false\n"
    "After the tool finishes, reply with ONLY: spill ok"
)

_PROGRESS_STEPS_LIVE_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages || [];
  for (const msg of msgs) {
    if (msg.role !== 'assistant') continue;
    const metaSteps = Array.isArray(msg.metadata?.progressSteps)
      ? msg.metadata.progressSteps
      : [];
    const steps = (msg.progressSteps?.length ? msg.progressSteps : metaSteps) || [];
    const step = steps.find((s) => s && s.evicted_file_ref);
    if (step) {
      return {
        ready: true,
        ref: step.evicted_file_ref,
        hasStdout: !!step.stdout,
      };
    }
  }
  return { ready: false, count: msgs.length };
})()"""

_EXPAND_PROGRESS_PANEL_JS = """(() => {
  const viewFull = Array.from(document.querySelectorAll('button')).find(
    (el) => /View Full Output|查看完整输出|完整输出を表示|전체 출력 보기/.test(el.textContent || ''),
  );
  if (viewFull) return { ready: true, alreadyVisible: true };
  const header = Array.from(document.querySelectorAll('h3')).find(
    (el) => /Task Steps|任务步骤|Task|任务|タスク|작업/.test(el.textContent || ''),
  );
  if (!header) return { ready: false, reason: 'no-task-header' };
  const toggleRow = header.closest('.cursor-pointer');
  if (!(toggleRow instanceof HTMLElement)) return { ready: false, reason: 'no-toggle-row' };
  toggleRow.click();
  return { ready: true, clicked: true };
})()"""

_WAIT_PROGRESS_UI_DOM_JS = """(() => {
  const header = Array.from(document.querySelectorAll('h3')).find(
    (el) => /Task Steps|任务步骤|Task|任务|タスク|작업/.test(el.textContent || ''),
  );
  const viewFull = Array.from(document.querySelectorAll('button')).find(
    (el) => /View Full Output|查看完整输出|完整输出を表示|전체 출력 보기/.test(el.textContent || ''),
  );
  return { ready: !!header || !!viewFull, hasHeader: !!header, hasViewFull: !!viewFull };
})()"""

_TERMINAL_PREVIEW_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTruncated = /LARGE OUTPUT TRUNCATED|输出已截断|出力を切り詰め/.test(text);
  return { ready: hasTruncated, preview: text.slice(0, 400) };
})()"""

_VIEW_FULL_OUTPUT_JS = """(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(
    (el) => /View Full Output|查看完整输出|完整输出を表示|전체 출력 보기/.test(el.textContent || ''),
  );
  if (!btn) return { ready: false, clicked: false };
  btn.click();
  return { ready: true, clicked: true };
})()"""


def _kickoff_bash_fg_js(prompt: str) -> str:
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return {{ ok: false, err: 'no-sendChatMessage' }};
  bridge.setActionMode?.('agent');
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  const result = await bridge.sendChatMessage({json.dumps(prompt)}, {{
    baselineUserCount: usersBefore,
    waitForStreamCompletion: false,
  }});
  const snap = bridge.turnSnapshot?.() ?? {{}};
  return {{
    ...result,
    chatId: snap.chatId ?? result.chatId ?? null,
    actionMode: bridge.getActionMode?.() ?? null,
  }};
}})()"""


_BRIDGE_READY_JS = """(() => ({
  ready: typeof window.__MYRM_E2E_CHAT__?.sendChatMessage === 'function',
  hasSend: typeof window.__MYRM_E2E_CHAT__?.sendChatMessage === 'function',
  hasBridge: !!window.__MYRM_E2E_CHAT__,
}))()"""

_CLICK_NEW_CHAT_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (bridge?.resetChat) {
    bridge.resetChat();
    return { ready: true, mode: 'bridge-reset' };
  }
  if (document.querySelector('[data-chat-input]')) {
    return { ready: true, mode: 'already' };
  }
  const newBtn = Array.from(document.querySelectorAll('aside button')).find((b) => {
    const text = (b.textContent || '').trim();
    return text.includes('新对话') || text.includes('New chat');
  });
  if (newBtn) {
    newBtn.click();
    return { ready: true, mode: 'new-chat' };
  }
  return { ready: false, mode: 'no-button' };
})()"""

_WORKSPACE_READY_JS = """(async () => {
  const wait = window.__MYRM_WAIT_WORKSPACE_STREAM__;
  if (typeof wait !== 'function') {
    return { ready: false, err: 'missing-wait-hook' };
  }
  const result = await wait(30000);
  return { ready: result?.ok === true, ...result };
})()"""


def _drawer_ready_js(marker_line: str) -> str:
    encoded = json.dumps(marker_line)
    return f"""(() => {{
  const text = document.body?.innerText || '';
  return {{ ready: text.includes({encoded}), sample: text.slice(0, 500) }};
}})()"""


def _evaluate_dict(client, page, expression: str, *, timeout_sec: float) -> dict[str, object]:
    raw = client.evaluate(page, expression, timeout_sec=timeout_sec)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return {"value": raw}


def _create_foreground_bash_agent(client: httpx.Client, api_base: str) -> str:
    payload = {
        "name": f"Bash FG Evict {uuid.uuid4().hex[:6]}",
        "description": "Live foreground bash UECD Chrome E2E",
        "system_prompt": (
            "You run shell commands via bash_code_execute_tool when asked. "
            "For foreground requests use run_in_background=false and call the tool "
            "exactly once before replying."
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "enabled_builtin_tools": ["code_execute"],
        "security_overrides": {
            "yoloModeEnabled": True,
            "yolo_mode_enabled_at": time.time(),
        },
    }
    resp = client.post(f"{api_base}/api/v1/user-agents", json=payload, timeout=60.0)
    resp.raise_for_status()
    body = resp.json()
    agent_id = body.get("data", {}).get("id") or body.get("id")
    assert isinstance(agent_id, str) and agent_id
    probe = client.get(
        f"{api_base}/api/v1/security/allowlist/test/hitl-probe",
        params={"agent_id": agent_id},
        timeout=30.0,
    )
    probe.raise_for_status()
    probe_body = probe.json()
    assert probe_body.get("yolo") is True, probe_body
    assert probe_body.get("yolo_active") is True, probe_body
    return agent_id


def _bash_tool_seen_in_messages(messages: list[dict[str, object]]) -> bool:
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        meta = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
        steps_raw = msg.get("progressSteps") or meta.get("progressSteps")
        if not isinstance(steps_raw, list):
            continue
        for step in steps_raw:
            if not isinstance(step, dict):
                continue
            if step.get("tool_name") == _BASH_TOOL:
                return True
    return False


def _wait_spill_via_api(api_base: str, chat_id: str) -> str:
    deadline = time.monotonic() + _API_POLL_TIMEOUT_SEC
    last_messages = 0
    saw_bash = False
    while time.monotonic() < deadline:
        messages = fetch_chat_messages(chat_id, api_url=api_base)
        last_messages = len(messages)
        if _bash_tool_seen_in_messages(messages):
            saw_bash = True
        ref = _evicted_ref_from_messages(messages)
        if ref:
            return ref
        time.sleep(2.0)
    detail = f"messages={last_messages}; bash_tool={saw_bash}"
    raise AssertionError(
        f"No evicted_file_ref after UI LIVE turn for chat {chat_id} ({detail})"
    )


def _run_ui_live_bash_turn(
    client, page, *, agent_id: str, api_base: str
) -> str:
    dismiss_blocking_modals(client, page)

    bridge_ready = wait_for_state(client, page, _BRIDGE_READY_JS, timeout_sec=60.0)
    assert bridge_ready.get("ready") is True, json.dumps(bridge_ready, ensure_ascii=False)

    new_chat = wait_for_state(client, page, _CLICK_NEW_CHAT_JS, timeout_sec=30.0)
    assert new_chat.get("ready") is True, json.dumps(new_chat, ensure_ascii=False)

    workspace_ready = wait_for_state(
        client, page, _WORKSPACE_READY_JS, timeout_sec=45.0
    )
    assert workspace_ready.get("ready") is True, json.dumps(
        workspace_ready, ensure_ascii=False
    )

    kickoff = _evaluate_dict(
        client, page, _kickoff_bash_fg_js(_FG_PROMPT), timeout_sec=120.0
    )
    assert kickoff.get("ok") is True, json.dumps(kickoff, ensure_ascii=False)
    chat_id = str(kickoff.get("chatId") or "").strip()
    if not chat_id:
        path_state = wait_for_state(
            client,
            page,
            "(() => ({ path: location.pathname }))()",
            timeout_sec=15.0,
        )
        path = str(path_state.get("path") or "").strip("/")
        chat_id = path if path and path != agent_id else ""
    assert chat_id, json.dumps(kickoff, ensure_ascii=False)

    evicted_ref = _wait_spill_via_api(api_base, chat_id)
    assert _OUTPUT_BASENAME_RE.match(evicted_ref), evicted_ref
    _verify_evicted_file(api_base, chat_id, evicted_ref)
    return chat_id


def _evicted_ref_from_messages(messages: list[dict[str, object]]) -> str | None:
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        meta = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
        steps_raw = msg.get("progressSteps") or meta.get("progressSteps")
        if not isinstance(steps_raw, list):
            continue
        for step in steps_raw:
            if not isinstance(step, dict):
                continue
            ref = step.get("evicted_file_ref")
            if isinstance(ref, str) and ref:
                return ref
            alt = step.get("evicted_ref")
            if isinstance(alt, str) and alt:
                return alt
    return None


def _verify_evicted_file(api_base: str, chat_id: str, filename: str) -> None:
    query = urlencode(
        {
            "chat_id": chat_id,
            "filename": filename,
            "offset": 0,
            "limit": 0,
        }
    )
    payload = http_json("GET", f"{api_base}/api/v1/files/evicted?{query}")
    assert isinstance(payload, dict), payload
    content = str(payload.get("content") or "")
    assert _MARKER in content, content[:400]


def _run_drawer_flow(client, page, *, marker_line: str) -> None:
    dismiss_blocking_modals(client, page)
    loaded = wait_for_state(client, page, _PROGRESS_STEPS_LIVE_JS, timeout_sec=60.0)
    assert loaded.get("ready") is True, json.dumps(loaded, ensure_ascii=False)

    dom_ready = wait_for_state(client, page, _WAIT_PROGRESS_UI_DOM_JS, timeout_sec=90.0)
    assert dom_ready.get("ready") is True, json.dumps(dom_ready, ensure_ascii=False)

    expanded = wait_for_state(client, page, _EXPAND_PROGRESS_PANEL_JS, timeout_sec=30.0)
    assert expanded.get("ready") is True, json.dumps(expanded, ensure_ascii=False)

    terminal = wait_for_state(client, page, _TERMINAL_PREVIEW_JS, timeout_sec=60.0)
    assert terminal.get("ready") is True, json.dumps(terminal, ensure_ascii=False)

    clicked = wait_for_state(client, page, _VIEW_FULL_OUTPUT_JS, timeout_sec=60.0)
    assert clicked.get("clicked") is True, json.dumps(clicked, ensure_ascii=False)

    drawer = wait_for_state(
        client, page, _drawer_ready_js(marker_line), timeout_sec=45.0
    )
    assert drawer.get("ready") is True, json.dumps(drawer, ensure_ascii=False)


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.timeout(600)
def test_live_agent_bash_foreground_spill_evicted_api_and_drawer() -> None:
    """Live LLM via Chrome UI + foreground bash → UECD spill → API + Drawer."""
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready — configure default model in WebUI E2E profile"
        )

    api_base = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    last_error = ""

    for attempt in range(_MAX_UI_ATTEMPTS):
        try:
            with httpx.Client() as client:
                agent_id = _create_foreground_bash_agent(client, api_base)
                ensure_e2e_hitl_mode(api_url=api_base)
                reset_resp = client.post(
                    f"{api_base}/api/v1/security/allowlist/test/reset-hitl-runtime",
                    timeout=30.0,
                )
                reset_resp.raise_for_status()

            prepare_e2e_ui_session(api_base)
            agent_route = f"/?agentId={agent_id}"
            warm_ui_route(agent_route)

            with open_mcp_page(f"{ui_url}{agent_route}", timeout_ms=_PAGE_TIMEOUT_MS) as (
                client,
                page,
            ):
                chat_id = _run_ui_live_bash_turn(
                    client, page, agent_id=agent_id, api_base=api_base
                )
                warm_ui_route(f"/{chat_id}")
                _run_drawer_flow(client, page, marker_line=_MARKER)
            break
        except (AssertionError, httpx.HTTPError, httpx.TransportError) as exc:
            last_error = str(exc)
            if attempt >= _MAX_UI_ATTEMPTS - 1:
                raise AssertionError(last_error) from exc
            time.sleep(2.0)
    else:
        raise AssertionError(last_error or "bash foreground LIVE UI turn failed")
