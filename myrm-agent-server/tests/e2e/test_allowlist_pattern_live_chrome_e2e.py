"""Chrome LIVE_AGENT E2E: bash approval → allow-always pattern → Settings list.

Uses ``private_backend=True`` so chat/agent-stream hit an isolated ``:180xx`` API — never
contends with shared ``:8080`` agent-stream lock while parallel LIVE pytest runs.

Formal run::

    MYRM_E2E_LANE=LIVE_AGENT ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_allowlist_pattern_live_chrome_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    ensure_e2e_hitl_mode,
    ensure_e2e_hitl_mode_in_browser,
    ensure_e2e_onboarding_complete,
    fetch_chat_messages,
    fetch_config_value,
    get_e2e_api_url,
    hard_reset_e2e_hitl_mode,
    shared_hot_e2e_api_base,
    WAIT_WORKSPACE_STREAM_JS,
    STREAM_API_BINDING_JS,
    wait_e2e_provider_ready,
)
from cdp_chat_ui import chat_id_from_path  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.chrome_allowlist_live_e2e import (
    _AGENT_READY_JS,
    _APPROVAL_VISIBLE_JS,
    _CLICK_ALLOW_ALWAYS_JS,
    _CONFIRM_ALLOW_ALWAYS_DIALOG_JS,
    _RECOVER_HITL_JS,
    _RUNTIME_BINDING_JS,
    _SELECT_PATTERN_SCOPE_JS,
    _TURN_DONE_JS,
    SETTINGS_PATTERN_VISIBLE_JS,
)
from tests.support.chrome_allowlist_settings_e2e import SETTINGS_SECURITY_SHELL_READY_JS
from tests.support.chrome_mcp_e2e import get_e2e_ui_url, http_json, wait_for_state, warm_ui_route
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease


def _parse_browser_eval(raw: object) -> dict[str, object]:
    if isinstance(raw, str):
        try:
            return _parse_browser_eval(json.loads(raw))
        except json.JSONDecodeError:
            return {"value": raw}
    if isinstance(raw, dict):
        if "ready" in raw or "queueLen" in raw or "hasApprove" in raw:
            return raw
        inner = raw.get("value")
        if inner is not None and inner is not raw:
            nested = _parse_browser_eval(inner)
            if any(key in nested for key in ("ready", "queueLen", "hasApprove", "sample")):
                return nested
        return raw
    return {"value": raw}

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
_BASH_TOOL = "bash_code_execute_tool"
# Must be UNKNOWN risk (not SAFE like echo) or engine auto-allows without HITL dialog.
# Use a syntactically valid URL so the live model executes curl; connection refused is OK.
_PATTERN_COMMAND = "curl -sS http://127.0.0.1:9/ALLOWLIST_LIVE_PROBE"
# Matches deriveCommandPattern(first_two_tokens + " *") for the probe command.
_PATTERN_STORED = "curl -sS *"
# Natural-language user turn (no E2E_* / MUST injection — mimo rejects those in user text).
_USER_PROMPT = (
    "Run this shell connectivity probe exactly once with bash_code_execute_tool: "
    f"`{_PATTERN_COMMAND}`. Connection refused is expected."
)
_APPROVAL_WAIT_SEC = 240.0
_STALL_AFTER_STREAM_SEC = 90.0
_MAX_CHAT_ATTEMPTS = 2


def _hitl_probe(api_url: str, *, chat_id: str | None = None) -> dict[str, object]:
    from cdp_chat_support import _e2e_api_get_json

    query = f"chat_id={chat_id}" if chat_id else ""
    suffix = f"?{query}" if query else ""
    probe = _e2e_api_get_json(
        f"{api_url.rstrip('/')}/api/v1/security/allowlist/test/hitl-probe{suffix}",
        timeout_sec=15.0,
    )
    return probe if isinstance(probe, dict) else {}


def _pin_and_verify_hitl_mode(api_url: str) -> None:
    """Pin global securityConfig on private API and shared :8080 (YOLO drift guard)."""
    ensure_e2e_hitl_mode(api_url=api_url)
    targets: list[str] = [api_url.rstrip("/")]
    shared = shared_hot_e2e_api_base()
    if shared not in targets:
        targets.append(shared)
    for target in targets:
        ensure_e2e_onboarding_complete(api_url=target)
        cfg = fetch_config_value("securityConfig", api_url=target)
        if cfg.get("yoloModeEnabled") or cfg.get("yolo_mode_enabled"):
            raise AssertionError(f"LIVE E2E requires YOLO off on {target}; got {cfg!r}")
        perms = cfg.get("permissions")
        if isinstance(perms, dict) and str(perms.get("*", "")).lower() == "allow":
            raise AssertionError(f"LIVE E2E requires no permissions.*=allow on {target}; got {cfg!r}")
        probe = _hitl_probe(target)
        if probe.get("yolo") or probe.get("expects_ask") is not True:
            raise AssertionError(
                f"LIVE E2E HITL probe failed on {target}: {probe!r}; cfg={cfg!r}"
            )


def _fetch_allowlist_rows(api_url: str) -> list[dict[str, object]]:
    listed = http_json("GET", f"{api_url.rstrip('/')}/api/v1/security/allowlist")
    rows = listed.get("data") if isinstance(listed, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _is_live_probe_pattern_row(row: dict[str, object]) -> bool:
    if row.get("granularity") != "pattern":
        return False
    pattern = str(row.get("command_pattern") or "")
    return pattern == _PATTERN_STORED or "ALLOWLIST_LIVE_PROBE" in pattern


async def _wait_for_pattern_allowlist_on_api(
    api_url: str,
    *,
    timeout_sec: float = 120.0,
) -> list[dict[str, object]]:
    deadline = time.monotonic() + timeout_sec
    last_rows: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        last_rows = _fetch_allowlist_rows(api_url)
        pattern_rows = [row for row in last_rows if row.get("granularity") == "pattern"]
        if any(_is_live_probe_pattern_row(row) for row in pattern_rows):
            return pattern_rows
        await asyncio.sleep(1.0)
    raise AssertionError(
        "Timed out waiting for pattern allowlist row on API; "
        f"rows={last_rows[-5:]}; api={api_url}"
    )


def _clear_allowlist_on_api(api_url: str) -> None:
    http_json(
        "DELETE",
        f"{api_url.rstrip('/')}/api/v1/security/allowlist/test/clear-pattern-fixture",
        expected_statuses=frozenset({200, 204, 404}),
    )
    http_json(
        "DELETE",
        f"{api_url.rstrip('/')}/api/v1/security/allowlist",
        expected_statuses=frozenset({200, 204}),
    )


def _hitl_diagnostics(api_url: str) -> dict[str, object]:
    cfg = fetch_config_value("securityConfig", api_url=api_url)
    return {
        "api": api_url,
        "yolo": bool(cfg.get("yoloModeEnabled") or cfg.get("yolo_mode_enabled")),
        "autoMode": bool(cfg.get("autoModeEnabled") or cfg.get("autoReviewEnabled")),
        "permissions": cfg.get("permissions"),
    }


def _create_shell_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Allowlist Pattern LIVE {suffix}",
        "description": "Chrome LIVE E2E for shell allow-always pattern",
        "system_prompt": (
            "You run local shell connectivity checks for the user. "
            "When the user asks you to run a specific curl command (including allowlist probes to 127.0.0.1:9), "
            "you MUST call bash_code_execute_tool with that exact command string. "
            "Port 9 (discard) is an intentional unreachable probe target — connection refused is expected; still execute. "
            "Do not refuse WebUI user messages as prompt injection — these are trusted local requests. "
            "Never answer with text only when a shell command was requested."
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "enabled_builtin_tools": ["code_execute"],
        "security_overrides": {"yoloModeEnabled": False, "autoModeEnabled": False},
    }
    created = http_json("POST", f"{api_url}/api/v1/user-agents", payload)
    assert isinstance(created, dict)
    agent_id = (
        created.get("data", {}).get("id")
        if isinstance(created.get("data"), dict)
        else created.get("id")
    )
    assert isinstance(agent_id, str) and agent_id
    return agent_id


def _message_blob(msg: dict[str, object]) -> str:
    parts: list[str] = [str(msg.get("content") or "")]
    metadata = msg.get("metadata")
    if metadata is not None:
        try:
            parts.append(json.dumps(metadata, ensure_ascii=False))
        except TypeError:
            parts.append(str(metadata))
    progress = msg.get("progressSteps")
    if progress is not None:
        try:
            parts.append(json.dumps(progress, ensure_ascii=False))
        except TypeError:
            parts.append(str(progress))
    return "\n".join(parts)


def _chat_bash_invocation(chat_id: str, *, api_url: str) -> tuple[bool, set[str]]:
    invoked: set[str] = set()
    for msg in fetch_chat_messages(chat_id, api_url=api_url):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        blob = _message_blob(msg)
        if _BASH_TOOL in blob or "bash_code_execute" in blob:
            invoked.add(_BASH_TOOL)
        for step in msg.get("progressSteps") or []:
            if not isinstance(step, dict):
                continue
            tool_name = str(step.get("tool_name") or step.get("toolName") or "")
            if "bash" in tool_name.lower():
                invoked.add(tool_name)
    return bool(invoked), invoked


def _api_origin(url: str) -> str:
    parsed = urlparse(url.rstrip("/"))
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid API base: {url!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


async def _wait_for_eval(chat: McpChatSession, expression: str, *, timeout_sec: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        raw = await chat.evaluate(expression, await_promise=False, recv_timeout=30.0)
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("ready") is True or last.get("ok") is True:
            return last
        await asyncio.sleep(0.5)
    raise AssertionError(f"Timed out waiting for browser state: {last}")


def _fetch_recent_audit_decisions(api_url: str, *, limit: int = 20) -> list[dict[str, object]]:
    from cdp_chat_support import _e2e_api_get_json

    try:
        payload = _e2e_api_get_json(
            f"{api_url.rstrip('/')}/api/v1/security/audit/logs?limit={limit}",
            timeout_sec=15.0,
        )
    except Exception:
        return []
    rows = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        rows = payload.get("logs") if isinstance(payload, dict) else None
    return [row for row in rows or [] if isinstance(row, dict)]


def _bash_auto_executed_text(*samples: str) -> bool:
    blob = "\n".join(samples)
    return any(marker in blob for marker in _BASH_AUTO_EXECUTED_MARKERS)


_BASH_AUTO_EXECUTED_MARKERS = (
    "命令执行完成",
    "命令已执行完毕",
    "已执行完成",
    "Command execution complete",
    "curl 退出码",
    "exit code 7",
    "Couldn't connect to server",
    "连接失败",
    "## 执行结果",
    "探针结果",
)


async def _assert_fresh_chat_surface(chat: McpChatSession) -> None:
    """Fail fast when resetChat left an old thread (stale POOLED security + history)."""
    raw = await chat.evaluate(
        """(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {})()""",
        await_promise=False,
        recv_timeout=10.0,
    )
    snap = raw if isinstance(raw, dict) else {}
    user_count = int(snap.get("userCount") or 0)
    if user_count > 0:
        raise AssertionError(
            "Expected a fresh chat after resetChat before LIVE approval turn; "
            f"snapshot={snap!r}"
        )


async def _wait_agent_applied(chat: McpChatSession, *, timeout_sec: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        raw = await chat.evaluate(_AGENT_READY_JS, await_promise=False, recv_timeout=20.0)
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("ready") is True:
            return
        await asyncio.sleep(1.0)
    raise AssertionError(f"E2E chat bridge not ready for shell agent: {last}")


async def _assert_stream_api_binding(chat: McpChatSession, *, expected_api: str) -> None:
    """Fail fast when chat stream would hit Next /api/v1 proxy (:8080 YOLO drift)."""
    expected_origin = _api_origin(expected_api)
    raw = await chat.evaluate(STREAM_API_BINDING_JS, await_promise=False, recv_timeout=15.0)
    binding = raw if isinstance(raw, dict) else {}
    if binding.get("usesRelativeProxy") is True or binding.get("hasPrivateBinding") is not True:
        raise AssertionError(
            "SHPOIB stream binding missing — agent-stream may hit shared :8080; "
            f"binding={binding!r}; expected={expected_origin!r}"
        )
    bound = str(binding.get("origin") or "").strip()
    if _api_origin(bound) != expected_origin:
        raise AssertionError(
            f"SHPOIB stream binding mismatch: expected={expected_origin!r} got={binding!r}"
        )


async def _assert_runtime_binding(chat: McpChatSession, *, expected_api: str) -> None:
    expected_origin = _api_origin(expected_api)
    raw = await chat.evaluate(_RUNTIME_BINDING_JS, await_promise=False, recv_timeout=15.0)
    binding = raw if isinstance(raw, dict) else {}
    bound = str(binding.get("apiBase") or binding.get("runtimeApi") or "").strip()
    if _api_origin(bound) != expected_origin:
        raise AssertionError(
            f"SHPOIB runtime binding mismatch: expected={expected_origin!r} got={binding!r}"
        )


async def _wait_for_shell_approval_ui(
    chat: McpChatSession,
    chat_id: str,
    *,
    api_url: str,
    timeout_sec: float = _APPROVAL_WAIT_SEC,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last_ui: dict[str, object] = {}
    last_invoked: set[str] = set()
    stream_idle_since: float | None = None
    last_recover_at: float = 0.0
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        await chat.dismiss_modals()
        raw = await chat.evaluate(_APPROVAL_VISIBLE_JS, await_promise=False, recv_timeout=20.0)
        last_ui = _parse_browser_eval(raw)
        if last_ui.get("ready") is True:
            return last_ui

        has_bash, invoked = _chat_bash_invocation(chat_id, api_url=api_url)
        last_invoked = invoked
        bridge = await chat.evaluate(
            """(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {})()""",
            await_promise=False,
            recv_timeout=10.0,
        )
        bridge_snap = bridge if isinstance(bridge, dict) else {}
        assistant_sample = str(bridge_snap.get("lastAssistantSample") or "")
        ui_sample = str(last_ui.get("sample") or "")
        if has_bash and not last_ui.get("ready"):
            if _bash_auto_executed_text(ui_sample, assistant_sample):
                probe = _hitl_probe(api_url)
                audit = _fetch_recent_audit_decisions(api_url)
                bash_audit = [
                    row
                    for row in audit
                    if "bash" in str(row.get("tool_name", "")).lower()
                    or "bash" in str(row.get("tool", "")).lower()
                ]
                raise AssertionError(
                    "bash auto-executed without approval (YOLO/config drift or SAFE bypass); "
                    f"ui={last_ui}; invoked={sorted(invoked)}; hitl_probe={probe}; "
                    f"audit={bash_audit[-5:] or audit[-5:]}; api={api_url}"
                )
            now = time.monotonic()
            if now - last_recover_at >= 5.0:
                last_recover_at = now
                try:
                    recover_raw = await chat.evaluate(
                        f"({ _RECOVER_HITL_JS })({json.dumps(chat_id)})",
                        await_promise=True,
                        recv_timeout=20.0,
                    )
                except RuntimeError as exc:
                    if "timed out" not in str(exc).lower():
                        raise
                    recover_raw = {"ok": False, "err": "mcp-eval-timeout"}
                if isinstance(recover_raw, dict) and int(recover_raw.get("queueLen") or 0) > 0:
                    continue
        is_streaming = bridge_snap.get("isStreaming") is True
        if is_streaming:
            stream_idle_since = None
        elif stream_idle_since is None:
            stream_idle_since = time.monotonic()

        if isinstance(bridge_snap, dict) and not is_streaming:
            sample = assistant_sample
            if sample.strip() and not has_bash:
                raise AssertionError(
                    "Model finished without invoking bash_code_execute_tool; "
                    f"assistant={sample[:400]!r}; ui={last_ui}; api={api_url}"
                )
            if (
                stream_idle_since is not None
                and not has_bash
                and time.monotonic() - stream_idle_since >= _STALL_AFTER_STREAM_SEC
            ):
                raise AssertionError(
                    "Stream idle without bash_code_execute_tool; "
                    f"idle_sec={time.monotonic() - stream_idle_since:.0f}; "
                    f"ui={last_ui}; api={api_url}"
                )
            if has_bash and not last_ui.get("hasDialog") and stream_idle_since is not None:
                idle = time.monotonic() - stream_idle_since
                if idle >= 120.0:
                    diag = _hitl_diagnostics(api_url)
                    shared_diag = _hitl_diagnostics(shared_hot_e2e_api_base())
                    sse_probe = await chat.evaluate(
                        """(() => ({
                          sse: window.__MYRM_E2E_CHAT__?.sseSnapshot?.() ?? [],
                          attach: window.__MYRM_E2E_ATTACH_DIAG__ ?? null,
                          workspace: window.__MYRM_WORKSPACE_STREAM_STATUS__?.() ?? null,
                          multiplex: window.__MYRM_MULTIPLEX_STATS__?.() ?? null,
                        }))()""",
                        await_promise=False,
                        recv_timeout=10.0,
                    )
                    audit = _fetch_recent_audit_decisions(api_url)
                    hitl = _hitl_probe(api_url, chat_id=chat_id)
                    raise AssertionError(
                        "bash invoked on API but ToolApproval dialog never opened; "
                        f"idle_sec={idle:.0f}; ui={last_ui}; invoked={sorted(invoked)}; "
                        f"diag={sse_probe}; hitl={hitl}; audit={audit[-8:]}; "
                        f"private={diag}; shared={shared_diag}"
                    )
        await asyncio.sleep(1.0)

    raise AssertionError(
        "Shell approval UI did not appear; "
        f"ui={last_ui}; invoked={sorted(last_invoked)}; api={api_url}"
    )


async def _run_live_pattern_flow(chat: McpChatSession, agent_id: str, *, api_url: str) -> str:
    agent_url = f"{get_e2e_ui_url()}/?agentId={agent_id}"
    await chat.dismiss_modals()
    await _wait_agent_applied(chat)
    await _assert_runtime_binding(chat, expected_api=api_url)
    await hard_reset_e2e_hitl_mode(chat, api_url=api_url, page_url=agent_url)
    await _wait_agent_applied(chat)
    await chat.click_new_chat()
    await chat.ensure_chat_surface(BASE_URL)
    await _assert_fresh_chat_surface(chat)

    _pin_and_verify_hitl_mode(api_url)
    await ensure_e2e_hitl_mode_in_browser(chat)
    await _assert_stream_api_binding(chat, expected_api=api_url)
    workspace_ready = await _wait_for_eval(
        chat, WAIT_WORKSPACE_STREAM_JS, timeout_sec=45.0
    )
    assert workspace_ready.get("ok") is True, (
        f"Workspace multiplex stream not ready before LIVE turn: {workspace_ready!r}; api={api_url}"
    )
    send_result = await chat.send_message(_USER_PROMPT, _USER_PROMPT)
    chat_id_hint = str(
        send_result.get("started", {}).get("chatId")
        or send_result.get("submit", {}).get("chatId")
        or ""
    ).strip()

    started = await chat.wait_stream_started(
        _USER_PROMPT, timeout_sec=120.0, chat_id_hint=chat_id_hint or None
    )
    chat_id = chat_id_hint or str(started.get("chatId") or "").strip() or None
    if not chat_id:
        after_start = await chat.main_state(_USER_PROMPT, recv_timeout=30.0)
        chat_id = (
            chat_id_from_path(str(after_start.get("path") or ""))
            or str(after_start.get("bridgeChatId") or "").strip()
            or None
        )
    assert chat_id, f"Expected chat id after stream start: started={started}; send={send_result}"

    # Stay on the streaming tab — mid-stream Page.navigate drops SSE approval events.
    path_probe = await chat.evaluate(
        "(() => ({ path: location.pathname }))()",
        await_promise=False,
        recv_timeout=10.0,
    )
    current_path = str(path_probe.get("path") or "") if isinstance(path_probe, dict) else ""
    if current_path != f"/{chat_id}":
        await chat.navigate_to_chat(chat_id, BASE_URL, timeout_sec=90.0)
    await _assert_runtime_binding(chat, expected_api=api_url)
    await _assert_stream_api_binding(chat, expected_api=api_url)
    await _wait_for_shell_approval_ui(chat, chat_id, api_url=api_url, timeout_sec=_APPROVAL_WAIT_SEC)

    click_always = await chat.evaluate(_CLICK_ALLOW_ALWAYS_JS, await_promise=False)
    assert isinstance(click_always, dict) and click_always.get("ok") is True, click_always
    await asyncio.sleep(0.8)

    select_scope = await chat.evaluate(
        _SELECT_PATTERN_SCOPE_JS,
        await_promise=True,
        recv_timeout=20.0,
    )
    assert isinstance(select_scope, dict) and select_scope.get("ok") is True, select_scope
    await asyncio.sleep(0.3)

    confirm = await chat.evaluate(_CONFIRM_ALLOW_ALWAYS_DIALOG_JS, await_promise=False)
    assert isinstance(confirm, dict) and confirm.get("ok") is True, confirm

    await _wait_for_pattern_allowlist_on_api(api_url, timeout_sec=120.0)
    return chat_id


@pytest.fixture(autouse=True)
def _clear_allowlist_before_live(_chrome_e2e_item_runtime: object | None) -> None:
    api_base = get_e2e_api_url()
    _pin_and_verify_hitl_mode(api_base)
    _clear_allowlist_on_api(api_base)
    yield
    _clear_allowlist_on_api(api_base)


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.asyncio
async def test_live_agent_shell_allow_always_pattern_settings_roundtrip(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail("Provider not ready — seed WebUI model via chrome-e2e-model-seed.mjs")

    api_base = get_e2e_api_url()
    _pin_and_verify_hitl_mode(api_base)
    ui_base = get_e2e_ui_url()
    agent_id = _create_shell_agent(api_base)
    e2e_resource_ledger.register("agent", agent_id)

    client = ChromeMcpClient(request_timeout_sec=180.0)
    await asyncio.to_thread(client.start)
    try:
        page: McpPage | None = None
        agent_url = f"{ui_base}/?agentId={agent_id}"
        last_error = ""
        chat_id = ""
        for attempt in range(1, _MAX_CHAT_ATTEMPTS + 1):
            heartbeat_e2e_lease()
            try:
                for page_attempt in range(3):
                    try:
                        page = await asyncio.to_thread(
                            client.new_page, agent_url, timeout_ms=120_000
                        )
                        break
                    except (TimeoutError, RuntimeError) as exc:
                        if page_attempt >= 2 or "new_page" not in str(exc):
                            raise
                        await asyncio.sleep(2.0 * (page_attempt + 1))
                if page is None:
                    raise RuntimeError("new_page returned no page")
                chat = McpChatSession(client, page)
                await chat.bootstrap(agent_url, timeout_sec=120.0)
                chat_id = await _run_live_pattern_flow(chat, agent_id, api_url=api_base)
                e2e_resource_ledger.register("chat", chat_id)
                break
            except (AssertionError, RuntimeError, TimeoutError) as exc:
                last_error = str(exc)
                if attempt >= _MAX_CHAT_ATTEMPTS:
                    raise
                await asyncio.sleep(2.0)
        else:
            pytest.fail(last_error or "live pattern flow failed")
        assert chat_id

        listed = http_json("GET", f"{api_base}/api/v1/security/allowlist")
        rows = listed.get("data") if isinstance(listed, dict) else None
        assert isinstance(rows, list) and len(rows) >= 1, listed
        pattern_rows = [row for row in rows if row.get("granularity") == "pattern"]
        assert pattern_rows, rows
        assert any(_is_live_probe_pattern_row(row) for row in pattern_rows)

        warm_ui_route("/settings/security")
        await asyncio.to_thread(
            client.navigate, page, f"{ui_base}/settings/security", timeout_ms=90_000
        )
        shell = await asyncio.to_thread(
            wait_for_state,
            client,
            page,
            SETTINGS_SECURITY_SHELL_READY_JS,
            timeout_sec=90.0,
        )
        assert shell.get("ready") is True, shell
        visible = await asyncio.to_thread(
            wait_for_state,
            client,
            page,
            SETTINGS_PATTERN_VISIBLE_JS,
            timeout_sec=60.0,
        )
        assert visible.get("ready") is True, visible
    finally:
        client.close()
