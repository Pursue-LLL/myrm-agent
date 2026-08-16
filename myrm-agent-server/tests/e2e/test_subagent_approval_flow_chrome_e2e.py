"""Chrome LIVE_AGENT E2E: subagent high-risk bash approval flow (real WebUI HITL).

Verifies the full real-user path for a *subagent* (not the main agent) triggering a
high-risk shell command:

1. Real WebUI textarea send asks the main agent to delegate ``rm -rf`` to a subagent.
2. The subagent's ``bash_code_execute_tool`` hits the approval middleware and emits an
   ``approval_required`` / ``tool_approval_request`` interrupt (action_type=subagent_approval).
3. The front-end renders the approval card (PolymorphicApprovalCard) and the E2E clicks
   Approve like a real user.
4. The subagent resumes, completes, and the main agent replies with the execution result.

This closes the coverage gap left by ``test_subagent_interrupt_e2e.py`` (in-process
TestClient cannot bridge the approval event) and by ``test_subagent_dashboard_ui_chrome_e2e.py``
(which seeds YOLO to skip HITL entirely).

Formal run::

    MYRM_E2E_LANE=LIVE_AGENT ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_subagent_approval_flow_chrome_e2e.py
"""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import (  # noqa: E402
    STREAM_API_BINDING_JS,
    WAIT_WORKSPACE_STREAM_JS,
    ensure_e2e_hitl_mode,
    ensure_e2e_hitl_mode_in_browser,
    ensure_e2e_onboarding_complete,
    fetch_config_value,
    get_e2e_api_url,
    shared_hot_e2e_api_base,
    wait_e2e_provider_ready,
)
from cdp_chat.ui import chat_id_from_path  # noqa: E402
from chrome_mcp.client import ChromeMcpClient, McpPage  # noqa: E402
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.support.chrome_allowlist_live_e2e import (
    _APPROVAL_VISIBLE_JS,
)
from tests.support.chrome_mcp_e2e import (
    guarded_httpx_request,
    http_json,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once

_BASH_TOOL = "bash_code_execute_tool"
_APPROVAL_WAIT_SEC = 300.0
_MAX_CHAT_ATTEMPTS = 2

# UNKNOWN-risk command (rm -rf) so the engine asks instead of auto-allowing.
_TARGET_DIR = "/tmp/myrm_e2e_subagent_approval"
_USER_PROMPT = (
    f"请使用 delegate_task_tool 创建一个 test_bash 子智能体（wait=true 同步等待），"
    f"让它执行 bash_code_execute_tool 命令：`rm -rf {_TARGET_DIR}`。"
    "执行完成后立即汇报结果并结束，不要做其它操作。"
)

_AGENT_SYSTEM_PROMPT = (
    "You are a helpful agent. When the user asks you to delegate a bash task to a subagent, "
    "use delegate_task_tool with agent_type='test_bash' and wait=true. "
    "The subagent has only bash_code_execute_tool. Report the subagent's result when it finishes."
)

_SUBAGENT_READY_JS = """(() => {
  const layout = document.querySelector('[data-testid="app-layout"]');
  const input = document.querySelector('[data-chat-input]');
  const fiberKey = input
    ? Object.keys(input).find((k) => k.startsWith('__reactFiber$'))
    : null;
  return {
    href: location.href,
    ready: !!input && !!window.__MYRM_E2E_CHAT__?.handleSubmit,
    hasLayout: !!layout,
    hasInput: !!input,
    clientHydrated: !!fiberKey,
    hasBridge: !!window.__MYRM_E2E_CHAT__,
  };
})()"""

_CLICK_APPROVE_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const approve = buttons.find((btn) => /Approve|批准/.test((btn.textContent || '').trim()));
  if (!approve) {
    return { ok: false, err: 'approve-button-not-found' };
  }
  approve.scrollIntoView({ block: 'center' });
  approve.click();
  return { ok: true, label: (approve.textContent || '').trim() };
})()"""


def _hitl_probe(api_url: str) -> dict[str, object]:
    from cdp_chat.support import _e2e_api_get_json

    probe = _e2e_api_get_json(
        f"{api_url.rstrip('/')}/api/v1/security/allowlist/test/hitl-probe",
        timeout_sec=15.0,
    )
    return probe if isinstance(probe, dict) else {}


def _pin_and_verify_hitl_mode(api_url: str) -> None:
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
        probe = _hitl_probe(target)
        if probe.get("yolo") or probe.get("expects_ask") is not True:
            raise AssertionError(
                f"LIVE E2E HITL probe failed on {target}: {probe!r}; cfg={cfg!r}"
            )


def _create_delegating_agent(api_url: str) -> str:
    import httpx

    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Subagent Approval LIVE {suffix}",
        "description": "Chrome LIVE E2E for subagent high-risk bash approval",
        "system_prompt": _AGENT_SYSTEM_PROMPT,
        "skill_ids": [],
        "mcp_ids": [],
        "enabled_builtin_tools": ["code_execute", "subagent"],
        "ephemeral_subagents": {
            "test_bash": {
                "system_prompt": "You are a bash execution worker.",
                "tools": ["bash_code_execute_tool"],
            }
        },
        "security_overrides": {"yoloModeEnabled": False, "autoModeEnabled": False},
    }
    with httpx.Client(base_url=api_url, timeout=60.0) as client:
        resp = guarded_httpx_request(
            client, "POST", f"{api_url}/api/v1/user-agents", json=payload, timeout=60.0
        )
        resp.raise_for_status()
    body = resp.json()
    agent_id = (
        body.get("data", {}).get("id")
        if isinstance(body.get("data"), dict)
        else body.get("id")
    )
    assert isinstance(agent_id, str) and agent_id
    return agent_id


async def _assert_stream_binding(chat: McpChatSession, *, expected_api: str) -> None:
    raw = await chat.evaluate(STREAM_API_BINDING_JS, intent=EvaluateIntent.SYNC_PROBE)
    binding = raw if isinstance(raw, dict) else {}
    if (
        binding.get("usesRelativeProxy") is True
        or binding.get("hasPrivateBinding") is not True
    ):
        raise AssertionError(
            f"SHPOIB stream binding missing: {binding!r}; expected={expected_api!r}"
        )
    bound = str(binding.get("origin") or "").strip()
    if bound not in (expected_api.rstrip("/"), ""):
        raise AssertionError(
            f"SHPOIB stream binding mismatch: expected={expected_api!r} got={binding!r}"
        )


async def _wait_for_approval_ui(
    chat: McpChatSession,
    *,
    api_url: str,
    timeout_sec: float = _APPROVAL_WAIT_SEC,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last_ui: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_once()
        await chat.dismiss_modals()
        raw = await chat.evaluate(
            _APPROVAL_VISIBLE_JS, intent=EvaluateIntent.BRIDGE_POLL
        )
        value = raw
        if isinstance(value, dict) and "ready" in value:
            last_ui = value
        else:
            last_ui = {"ready": False, "raw": value}
        if last_ui.get("ready") is True:
            return last_ui
        await asyncio.sleep(1.5)
    raise AssertionError(
        f"Approval UI did not appear within {timeout_sec}s: {last_ui!r}"
    )


async def _run_approval_flow(
    chat: McpChatSession,
    agent_id: str,
    *,
    api_url: str,
    ui_base: str,
) -> str:
    agent_url = f"{ui_base}/?agentId={agent_id}"
    await chat.bootstrap(agent_url, timeout_sec=120.0)
    _pin_and_verify_hitl_mode(api_url)
    await ensure_e2e_hitl_mode_in_browser(chat)
    await _assert_stream_binding(chat, expected_api=api_url)

    workspace_ready = await chat.evaluate(
        WAIT_WORKSPACE_STREAM_JS,
        intent=EvaluateIntent.AGENT_SUBMIT,
        timeout_sec=45.0,
    )
    assert (workspace_ready or {}).get(
        "ok"
    ) is True, f"Workspace stream not ready: {workspace_ready!r}; api={api_url}"

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
        after_start = await chat.main_state(
            _USER_PROMPT, intent=EvaluateIntent.BRIDGE_POLL
        )
        chat_id = (
            chat_id_from_path(str(after_start.get("path") or ""))
            or str(after_start.get("bridgeChatId") or "").strip()
            or None
        )
    assert (
        chat_id
    ), f"Expected chat id after stream start: started={started}; send={send_result}"

    # Stay on the streaming tab — mid-stream Page.navigate drops SSE approval events.
    path_probe = await chat.evaluate(
        "(() => ({ path: location.pathname }))()",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    current_path = (
        str(path_probe.get("path") or "") if isinstance(path_probe, dict) else ""
    )
    if current_path != f"/{chat_id}":
        await chat.navigate_to_chat(chat_id, ui_base, timeout_sec=90.0)

    approval = await _wait_for_approval_ui(chat, api_url=api_url)
    assert approval.get("queueLen") is not None
    assert (
        approval.get("hasApprove") is True
    ), f"Approval card missing Approve button: {approval}"

    click = await chat.evaluate(_CLICK_APPROVE_JS, intent=EvaluateIntent.SYNC_PROBE)
    assert isinstance(click, dict) and click.get("ok") is True, click

    # After approval the subagent resumes and completes; the main agent replies.
    deadline = time.monotonic() + 180.0
    last_snap: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_once()
        raw = await chat.evaluate(
            "(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {})()",
            intent=EvaluateIntent.BRIDGE_POLL,
        )
        snap = raw if isinstance(raw, dict) else {}
        last_snap = snap
        assistant_sample = str(snap.get("lastAssistantSample") or "")
        if assistant_sample and (
            "执行" in assistant_sample
            or "完成" in assistant_sample
            or "deleted" in assistant_sample
            or "rm" in assistant_sample.lower()
        ):
            return chat_id
        await asyncio.sleep(2.0)
    raise AssertionError(
        f"Agent did not reply after approval within 180s: {last_snap!r}"
    )


@pytest.fixture(autouse=True)
def _pin_hitl_before(_chrome_e2e_item_runtime: object | None) -> None:
    api_base = get_e2e_api_url()
    _pin_and_verify_hitl_mode(api_base)
    yield


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.asyncio
async def test_subagent_approval_flow_approve_resumes_chrome_e2e(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider not ready — seed WebUI model via chrome-e2e-model-seed.mjs"
        )

    api_base = get_e2e_api_url()
    _pin_and_verify_hitl_mode(api_base)
    ui_base = "http://127.0.0.1:3000"
    agent_id = _create_delegating_agent(api_base)
    e2e_resource_ledger.register("agent", agent_id)

    client = ChromeMcpClient(request_timeout_sec=180.0)
    await asyncio.to_thread(client.start)
    try:
        page: McpPage | None = None
        last_error = ""
        chat_id = ""
        for attempt in range(1, _MAX_CHAT_ATTEMPTS + 1):
            heartbeat_once()
            try:
                page = await asyncio.to_thread(
                    client.new_page,
                    f"{ui_base}/?agentId={agent_id}",
                    timeout_ms=120_000,
                )
                chat = McpChatSession(client, page)
                chat_id = await _run_approval_flow(
                    chat, agent_id, api_url=api_base, ui_base=ui_base
                )
                e2e_resource_ledger.register("chat", chat_id)
                break
            except (AssertionError, RuntimeError, TimeoutError) as exc:
                last_error = str(exc)
                if attempt >= _MAX_CHAT_ATTEMPTS:
                    raise
                await asyncio.sleep(2.0)
        else:
            pytest.fail(last_error or "subagent approval flow failed")
        assert chat_id

        # Final API-level evidence: subagent completed after approval.
        rows = http_json("GET", f"{api_base}/api/v1/chats/{chat_id}/subagents")
        data = rows.get("data") if isinstance(rows, dict) else None
        assert isinstance(data, list), rows
        assert any(
            isinstance(row, dict) and row.get("status") == "completed" for row in data
        ), f"No completed subagent after approval: {rows}"
    finally:
        client.close()
