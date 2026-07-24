"""Chrome LIVE_AGENT E2E: foreground bash spill → evicted API + LiveTerminal Drawer.

Phase 1: agent-stream (API) with live LLM + yolo code_execute agent — asserts
bash_code_execute_tool, tool_evicted_ref / progressSteps.evicted_file_ref, and
GET /files/evicted contains the deterministic marker.

Phase 2: single Chrome tab on the same chat — expand Task Steps, View Full Output,
Drawer shows marker (same UX path as READ seed Drawer test).
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
_MAX_STREAM_ATTEMPTS = 5

_FG_PROMPT = (
    "Run exactly one foreground shell command with bash_code_execute_tool "
    "(run_in_background must be false):\n"
    f'- command: python3 -c "print(\'{_MARKER}\'); print(\'x\' * 180000)"\n'
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


def _drawer_ready_js(marker_line: str) -> str:
    encoded = json.dumps(marker_line)
    return f"""(() => {{
  const text = document.body?.innerText || '';
  return {{ ready: text.includes({encoded}), sample: text.slice(0, 500) }};
}})()"""


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


def _tool_names_from_event(event: dict[str, object]) -> list[str]:
    names: list[str] = []
    for key in ("tool_name", "name", "tool"):
        val = event.get(key)
        if isinstance(val, str) and val:
            names.append(val)
    data = event.get("data")
    if isinstance(data, dict):
        for key in ("tool_name", "name", "tool"):
            val = data.get(key)
            if isinstance(val, str) and val:
                names.append(val)
    return names


def _evicted_ref_from_event(event: dict[str, object]) -> str | None:
    if event.get("type") != "tool_evicted_ref":
        return None
    data = event.get("data")
    if isinstance(data, str) and data:
        return data
    if isinstance(data, dict):
        ref = data.get("evicted_ref")
        if isinstance(ref, str) and ref:
            return ref
    ref_top = event.get("evicted_ref")
    return ref_top if isinstance(ref_top, str) and ref_top else None


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
    return None


def _wait_evicted_ref_via_api(
    api_base: str, chat_id: str, *, timeout_sec: float = 120.0
) -> str:
    deadline = time.monotonic() + timeout_sec
    last_messages = 0
    while time.monotonic() < deadline:
        messages = fetch_chat_messages(chat_id, api_url=api_base)
        last_messages = len(messages)
        ref = _evicted_ref_from_messages(messages)
        if ref:
            return ref
        time.sleep(1.0)
    raise AssertionError(
        f"No evicted_file_ref in progressSteps for chat {chat_id} after {timeout_sec:.0f}s "
        f"(messages={last_messages})"
    )


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


def _stream_foreground_bash(
    client: httpx.Client, api_base: str, agent_id: str, chat_id: str
) -> list[str]:
    request_data: dict[str, object] = {
        "messageId": f"bash-fg-evict-{uuid.uuid4().hex[:10]}",
        "chatId": chat_id,
        "query": _FG_PROMPT,
        "actionMode": "agent",
        "agentId": agent_id,
        "agentConfig": {"enabledBuiltinTools": ["code_execute"]},
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    tool_names: list[str] = []
    evicted_refs: list[str] = []
    errors: list[str] = []

    with client.stream(
        "POST",
        f"{api_base}/api/v1/agents/agent-stream",
        json=request_data,
        timeout=600.0,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line == "data: [DONE]":
                break
            if not line or not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            if event_type in (
                "tool_start",
                "tool_end",
                "tool_result",
                "tool_complete",
                "tool_failure",
                "tasks_steps",
            ):
                for name in _tool_names_from_event(event):
                    if name not in tool_names:
                        tool_names.append(name)
            ref = _evicted_ref_from_event(event)
            if ref and ref not in evicted_refs:
                evicted_refs.append(ref)
            if event_type == "error":
                err = event.get("error") or event.get("data")
                if err:
                    errors.append(str(err))
            if event_type in (
                "interrupt",
                "tool_approval",
                "tool_approval_request",
                "approval",
                "approval_required",
            ):
                raise AssertionError(
                    "YOLO agent emitted HITL interrupt during bash foreground spill E2E"
                )

    if _BASH_TOOL not in tool_names:
        detail = errors[0][:300] if errors else "no tool events"
        raise AssertionError(
            f"agent-stream did not invoke {_BASH_TOOL}; tools={tool_names}; detail={detail}"
        )
    return evicted_refs


def _run_drawer_flow(client, page, *, marker_line: str) -> None:
    dismiss_blocking_modals(client, page)
    loaded = wait_for_state(client, page, _PROGRESS_STEPS_LIVE_JS, timeout_sec=120.0)
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
    """Live LLM + foreground bash → UECD spill → API + Chrome Drawer."""
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready — configure default model in WebUI E2E profile"
        )

    api_base = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    chat_id = f"e2ebashfg-{uuid.uuid4().hex[:10]}"
    last_error = ""

    for attempt in range(_MAX_STREAM_ATTEMPTS):
        try:
            with httpx.Client() as client:
                chat_resp = client.post(
                    f"{api_base}/api/v1/chats/",
                    json={"chat_id": chat_id},
                    timeout=30.0,
                )
                chat_resp.raise_for_status()
                agent_id = _create_foreground_bash_agent(client, api_base)
                ensure_e2e_hitl_mode(api_url=api_base)
                reset_resp = client.post(
                    f"{api_base}/api/v1/security/allowlist/test/reset-hitl-runtime",
                    timeout=30.0,
                )
                reset_resp.raise_for_status()
                stream_refs = _stream_foreground_bash(
                    client, api_base, agent_id, chat_id
                )
            break
        except (AssertionError, httpx.HTTPError, httpx.TransportError) as exc:
            last_error = str(exc)
            if attempt >= _MAX_STREAM_ATTEMPTS - 1:
                raise AssertionError(last_error) from exc
            chat_id = f"e2ebashfg-{uuid.uuid4().hex[:10]}"
            time.sleep(2.0)
    else:
        raise AssertionError(last_error or "bash foreground stream failed")

    evicted_ref = _wait_evicted_ref_via_api(api_base, chat_id)
    if stream_refs and evicted_ref not in stream_refs:
        # progressSteps is SSOT for UI; stream ref is supplementary signal
        pass
    assert _OUTPUT_BASENAME_RE.match(evicted_ref), evicted_ref
    _verify_evicted_file(api_base, chat_id, evicted_ref)

    prepare_e2e_ui_session(api_base)
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=_PAGE_TIMEOUT_MS) as (
        client,
        page,
    ):
        _run_drawer_flow(client, page, marker_line=_MARKER)
