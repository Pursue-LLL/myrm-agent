"""Chrome LIVE_AGENT E2E: foreground bash spill → evicted API + LiveTerminal Drawer.

Phase 1 (SSOT): API agent-stream — assert bash_code_execute_tool + tool_evicted_ref,
GET /files/evicted contains marker. No blind UI poll.

Phase 2 (UX): same chat_id in Chrome — Task Steps → View Full Output → Drawer marker.
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

from cdp_chat.support import (  # noqa: E402
    ensure_e2e_hitl_mode,
    fetch_chat_messages,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_ui_url,
    guarded_httpx_request,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)
from tests.support.evicted_drawer_selectors import (  # noqa: E402
    CLEAR_RESOURCE_TIMINGS_JS as _CLEAR_RESOURCE_TIMINGS_JS,
)
from tests.support.evicted_drawer_selectors import (
    EXPAND_PROGRESS_PANEL_JS as _EXPAND_PROGRESS_PANEL_JS,
)
from tests.support.evicted_drawer_selectors import (
    TERMINAL_PREVIEW_JS as _TERMINAL_PREVIEW_JS,
)
from tests.support.evicted_drawer_selectors import (
    VIEW_FULL_OUTPUT_JS as _VIEW_FULL_OUTPUT_JS,
)
from tests.support.evicted_drawer_selectors import (
    WAIT_PROGRESS_UI_DOM_JS as _WAIT_PROGRESS_UI_DOM_JS,
)
from tests.support.evicted_drawer_selectors import (
    drawer_ready_js,
    evicted_request_probe_js,
)

_MARKER = "UECD_BASH_FG_MARKER"
_BASH_TOOL = "bash_code_execute_tool"
_OUTPUT_BASENAME_RE = re.compile(r"^output_[a-f0-9]{8}\.txt$")
_EVICTED_BASENAME_IN_TEXT_RE = re.compile(r"output_[a-f0-9]{8}\.txt")
_PAGE_TIMEOUT_MS = 180_000
_MAX_STREAM_ATTEMPTS = 5
_STREAM_TIMEOUT_SEC = 240.0
# Keep enough unique lines to exceed UECD eviction threshold while reducing
# runtime variance versus the previous 25k-line payload.
_SPILL_SEQ_LINES = 20000
_SPILL_COMMAND = f"echo {_MARKER} && seq 1 {_SPILL_SEQ_LINES}"

_FG_PROMPT = (
    "Please run this command in the foreground using bash_code_execute_tool exactly once:\n"
    f"- command: {_SPILL_COMMAND}\n"
    "- run_in_background: false\n"
    "- timeout: 90\n"
    "- reason: live foreground bash spill UECD E2E\n"
    "Then reply with ONLY: spill ok\n"
    "Do NOT reply spill ok unless tool output contains LARGE OUTPUT TRUNCATED."
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


def _create_foreground_bash_agent(client: httpx.Client, api_base: str) -> str:
    payload = {
        "name": f"Bash FG Evict {uuid.uuid4().hex[:6]}",
        "description": "Live foreground bash UECD Chrome E2E",
        "system_prompt": (
            "You help users run shell commands via bash_code_execute_tool when asked. "
            "When the user requests a foreground shell command, call bash_code_execute_tool "
            "exactly once with run_in_background=false and the exact command string before replying. "
            "Never reply spill ok unless bash output was evicted (LARGE OUTPUT TRUNCATED)."
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "enabled_builtin_tools": ["code_execute"],
        "security_overrides": {
            "yoloModeEnabled": True,
            "yolo_mode_enabled_at": time.time(),
        },
    }
    resp = guarded_httpx_request(
        client, "POST", f"{api_base}/api/v1/user-agents", json=payload, timeout=60.0
    )
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


def _evicted_ref_from_text(text: str) -> str | None:
    match = _EVICTED_BASENAME_IN_TEXT_RE.search(text)
    if match and _OUTPUT_BASENAME_RE.match(match.group(0)):
        return match.group(0)
    return None


def _evicted_ref_from_steps(steps_raw: object) -> str | None:
    if not isinstance(steps_raw, list):
        return None
    for step in steps_raw:
        if not isinstance(step, dict):
            continue
        ref = step.get("evicted_file_ref") or step.get("evicted_ref")
        if isinstance(ref, str) and ref:
            return ref
    return None


def _evicted_ref_from_event(event: dict[str, object]) -> str | None:
    for key in ("evicted_file_ref", "evicted_ref", "filename", "ref"):
        val = event.get(key)
        if isinstance(val, str) and val:
            return val
    data = event.get("data")
    if isinstance(data, str) and data.strip():
        ref = data.strip()
        if _OUTPUT_BASENAME_RE.match(ref):
            return ref
        parsed = _evicted_ref_from_text(ref)
        if parsed:
            return parsed
    if isinstance(data, dict):
        for key in ("evicted_file_ref", "evicted_ref", "filename", "ref"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
        steps_ref = _evicted_ref_from_steps(data.get("progressSteps"))
        if steps_ref:
            return steps_ref
    if isinstance(data, list):
        steps_ref = _evicted_ref_from_steps(data)
        if steps_ref:
            return steps_ref
    for key in ("content", "stdout", "output", "result"):
        val = event.get(key)
        if isinstance(val, str):
            parsed = _evicted_ref_from_text(val)
            if parsed:
                return parsed
    return None


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


def _bash_spill_diagnostics(messages: list[dict[str, object]]) -> str:
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
            if step.get("tool_name") != _BASH_TOOL:
                continue
            stdout = str(step.get("stdout") or step.get("output") or "")
            command = str(step.get("command") or step.get("input") or "")
            status = str(step.get("status") or "")
            items = step.get("items")
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    command = command or str(item.get("code") or item.get("text") or "")
                    stdout = stdout or str(
                        item.get("stdout") or item.get("output") or ""
                    )
                    status = status or str(item.get("status") or "")
            content = str(msg.get("content") or "")
            truncated = (
                "LARGE OUTPUT TRUNCATED" in stdout
                or "LARGE OUTPUT TRUNCATED" in content
            )
            return (
                f"command={command!r} status={status!r} truncated_preview={truncated} "
                f"stdout_sample={stdout[:200]!r} content_sample={content[:200]!r}"
            )
    return "no bash progress step in persisted messages"


def _stream_foreground_bash_spill(
    client: httpx.Client, api_base: str, agent_id: str, chat_id: str
) -> str:
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
        timeout=_STREAM_TIMEOUT_SEC,
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
                "tool_evicted_ref",
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
    if not evicted_refs:
        for _ in range(5):
            messages = fetch_chat_messages(chat_id, api_url=api_base)
            api_ref = _evicted_ref_from_messages(messages)
            if api_ref:
                evicted_refs.append(api_ref)
                break
            time.sleep(1.5)
    if not evicted_refs:
        diag = _bash_spill_diagnostics(fetch_chat_messages(chat_id, api_url=api_base))
        raise AssertionError(
            f"agent-stream invoked {_BASH_TOOL} but emitted no tool_evicted_ref; "
            f"large-output eviction did not trigger ({diag})"
        )
    return evicted_refs[0]


def _verify_evicted_file(api_base: str, chat_id: str, filename: str) -> None:
    query = urlencode(
        {
            "chat_id": chat_id,
            "filename": filename,
            "offset": 0,
            "limit": 500,
        }
    )
    payload = http_json("GET", f"{api_base}/api/v1/files/evicted?{query}")
    assert isinstance(payload, dict), payload
    content = str(payload.get("content") or "")
    assert _MARKER in content, content[:400]


def _wait_evicted_progress_via_api(
    api_base: str, chat_id: str, *, timeout_sec: float = 90.0
) -> str:
    deadline = time.monotonic() + timeout_sec
    last_count = 0
    while time.monotonic() < deadline:
        messages = fetch_chat_messages(chat_id, api_url=api_base)
        ref = _evicted_ref_from_messages(messages)
        if ref:
            return ref
        last_count = len(messages)
        time.sleep(0.5)
    raise AssertionError(
        f"Assistant progressSteps missing evicted_file_ref for chat {chat_id} "
        f"after {timeout_sec:.0f}s (last_message_count={last_count})"
    )


def _persisted_bash_step_snapshot(api_base: str, chat_id: str) -> dict[str, object]:
    for msg in fetch_chat_messages(chat_id, api_url=api_base):
        if msg.get("role") != "assistant":
            continue
        meta = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
        steps_raw = msg.get("progressSteps") or meta.get("progressSteps")
        if not isinstance(steps_raw, list):
            continue
        for step in steps_raw:
            if not isinstance(step, dict):
                continue
            if step.get("tool_name") == _BASH_TOOL or step.get("evicted_file_ref"):
                return {
                    "tool_name": step.get("tool_name"),
                    "evicted_file_ref": step.get("evicted_file_ref"),
                    "has_stdout": bool(str(step.get("stdout") or "").strip()),
                    "stdout_head": str(step.get("stdout") or "")[:240],
                    "step_keys": sorted(step.keys()),
                }
    return {"tool_name": None, "evicted_file_ref": None, "has_stdout": False}


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
    clear_result = client.evaluate(page, _CLEAR_RESOURCE_TIMINGS_JS, timeout_sec=5.0)
    assert (
        isinstance(clear_result, dict) and clear_result.get("ready") is True
    ), clear_result

    client.evaluate(
        page,
        evicted_request_probe_js(expected_offset=0, expected_limit=500),
        timeout_sec=5.0,
    )

    clicked = wait_for_state(client, page, _VIEW_FULL_OUTPUT_JS, timeout_sec=120.0)
    if clicked.get("clicked") is not True:
        diag = wait_for_state(
            client,
            page,
            """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages || [];
  const steps = [];
  for (const msg of msgs) {
    if (msg.role !== 'assistant') continue;
    const metaSteps = Array.isArray(msg.metadata?.progressSteps) ? msg.metadata.progressSteps : [];
    const raw = (msg.progressSteps?.length ? msg.progressSteps : metaSteps) || [];
    for (const step of raw) steps.push(step);
  }
  return {
    ready: true,
    loading: store?.loading,
    isMessagesLoaded: store?.isMessagesLoaded,
    messageCount: msgs.length,
    testid: !!document.querySelector('[data-testid="evicted-view-full-output"]'),
    preCount: document.querySelectorAll('pre').length,
    h3Count: document.querySelectorAll('h3').length,
    evictedRefs: steps.map((s) => s?.evicted_file_ref).filter(Boolean),
    bashSteps: steps.filter((s) => String(s?.tool_name || '').includes('bash')).length,
  };
})()""",
            timeout_sec=10.0,
        )
        raise AssertionError(
            f"View Full Output button missing; ui_diag={json.dumps(diag, ensure_ascii=False)}"
        )
    assert clicked.get("clicked") is True, json.dumps(clicked, ensure_ascii=False)
    request_probe = wait_for_state(
        client,
        page,
        evicted_request_probe_js(expected_offset=0, expected_limit=500),
        timeout_sec=30.0,
    )
    assert request_probe.get("hit") is True, json.dumps(
        request_probe, ensure_ascii=False
    )
    assert request_probe.get("hasLimitZero") is False, json.dumps(
        request_probe, ensure_ascii=False
    )

    drawer = wait_for_state(
        client, page, drawer_ready_js(marker_line), timeout_sec=45.0
    )
    assert drawer.get("ready") is True, json.dumps(drawer, ensure_ascii=False)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.timeout(600)
def test_live_agent_bash_foreground_spill_evicted_api_and_drawer() -> None:
    """Live LLM: API stream spill SSOT + Chrome Drawer on same chat."""
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
                chat_resp = guarded_httpx_request(
                    client,
                    "POST",
                    f"{api_base}/api/v1/chats/",
                    json={"chat_id": chat_id},
                    timeout=30.0,
                )
                chat_resp.raise_for_status()
                agent_id = _create_foreground_bash_agent(client, api_base)
                ensure_e2e_hitl_mode(api_url=api_base)
                reset_resp = guarded_httpx_request(
                    client,
                    "POST",
                    f"{api_base}/api/v1/security/allowlist/test/reset-hitl-runtime",
                    timeout=30.0,
                )
                reset_resp.raise_for_status()
                evicted_ref = _stream_foreground_bash_spill(
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

    assert _OUTPUT_BASENAME_RE.match(evicted_ref), evicted_ref
    _verify_evicted_file(api_base, chat_id, evicted_ref)

    api_ref = _wait_evicted_progress_via_api(api_base, chat_id)
    assert api_ref == evicted_ref or _OUTPUT_BASENAME_RE.match(api_ref), api_ref
    step_snapshot = _persisted_bash_step_snapshot(api_base, chat_id)
    assert step_snapshot.get("evicted_file_ref"), step_snapshot

    prepare_e2e_ui_session(api_base)
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=_PAGE_TIMEOUT_MS) as (
        client,
        page,
    ):
        attach_result = wait_for_state(
            client,
            page,
            f"""(async () => {{
              try {{
                await window.__MYRM_E2E_CHAT__?.attachToChat?.({json.dumps(chat_id)});
                return {{ ready: true }};
              }} catch (error) {{
                return {{ ready: false, err: String(error) }};
              }}
            }})()""",
            timeout_sec=90.0,
        )
        assert attach_result.get("ready") is True, attach_result
        _run_drawer_flow(client, page, marker_line=_MARKER)
