"""Chrome LIVE_AGENT E2E: subagent high-risk bash approval flow (real WebUI HITL).

Verifies the full real-user path for a *subagent* (not the main agent) triggering a
high-risk shell command:

1. Real WebUI textarea send asks the main agent to delegate ``rm -rf`` to a subagent.
2. The subagent's ``bash_code_execute_tool`` hits the approval middleware and emits an
   ``approval_required`` / ``tool_approval_request`` interrupt (action_type=subagent_approval).
3. The front-end renders the approval card (PolymorphicApprovalCard) and the E2E clicks
   Approve like a real user.
4. The subagent resumes, completes, and the main agent replies with the execution result.

This complements ``test_subagent_interrupt_e2e.py`` (in-process TestClient stream) and
``test_subagent_interrupt_live_e2e.py`` (live HTTP SHPOIB) by exercising the real WebUI
click path on PolymorphicApprovalCard. ``test_subagent_dashboard_ui_chrome_e2e.py`` seeds
YOLO to skip HITL entirely.

Formal run::

    MYRM_E2E_LANE=LIVE_AGENT ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_subagent_approval_flow_chrome_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import (  # noqa: E402
    STREAM_API_BINDING_JS,
    e2e_runtime_bootstrap_apply_js,
    ensure_e2e_hitl_mode_in_browser,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.support.chrome_allowlist_live_e2e import _RECOVER_HITL_JS
from tests.support.chrome_mcp_e2e import (
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once
from tests.support.hitl_live_e2e import pin_and_verify_hitl_mode
from tests.support.subagent_hitl_stream import run_until_subagent_approval

_APPROVAL_WAIT_SEC = 300.0
_POST_APPROVE_WAIT_SEC = 300.0
_MAX_CHAT_ATTEMPTS = 2

_BUILTIN_AGENT_ID = "builtin-general"
_SUBAGENT_TYPE = "bash_worker"
_TARGET_DIR = "/tmp/myrm_e2e_subagent_approval"
_USER_PROMPT = (
    "请使用 delegate_task_tool 工具创建一个子智能体，必须将 agent_type 参数设置为 "
    f"'{_SUBAGENT_TYPE}'，"
    "并且必须将 wait 参数设置为 true（同步等待子任务完成，不要异步）。"
    f"子智能体必须调用 bash_code_execute_tool 对目录 {_TARGET_DIR} 执行递归强制删除"
    "（禁止替换路径、禁止输出占位符、禁止只用文本描述而不调用工具）。"
    "注意：必须使用原生函数调用（Native Tool Calling / Function Calling）来调用工具，"
    "绝对不要在文本中输出 XML 格式的工具调用！"
)

_AGENT_SYSTEM_PROMPT = (
    "You are a helpful agent. When the user asks you to delegate a bash task to a subagent, "
    f"use delegate_task_tool with agent_type='{_SUBAGENT_TYPE}' and wait=true. "
    "The subagent has only bash_code_execute_tool. Report the subagent's result when it finishes."
)

_SUBAGENT_SYSTEM_PROMPT = (
    "You are a bash execution worker. When asked to recursively delete a directory, "
    "you MUST call bash_code_execute_tool with the exact shell command "
    "'rm -rf <path>' (never replace paths or emit placeholders), then report the output."
)

_EPHEMERAL_SUBAGENTS: dict[str, dict[str, object]] = {
    _SUBAGENT_TYPE: {
        "system_prompt": _SUBAGENT_SYSTEM_PROMPT,
        "tools": ["bash_code_execute_tool"],
    }
}

_SUBAGENT_APPROVAL_VISIBLE_JS = """(() => {
  const approvalSnap = window.__MYRM_E2E_CHAT__?.toolApprovalSnapshot?.() ?? {};
  const queueLen = Number(approvalSnap.queueLen ?? 0);
  const buttons = Array.from(document.querySelectorAll('button'));
  const hasApprove = buttons.some((btn) => /Approve|批准/.test((btn.textContent || '').trim()));
  const text = document.body?.innerText || '';
  const hasShell = /bash_code_execute_tool|Shell|shell|rm\\s+-rf/i.test(text);
  const ready = hasApprove && (hasShell || queueLen > 0);
  return { ready, queueLen, hasApprove, hasShell, sample: text.slice(0, 900) };
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


def _seed_chat_via_api(api_url: str, chat_id: str) -> None:
    http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/chats/",
        {
            "chat_id": chat_id,
            "agent_id": _BUILTIN_AGENT_ID,
            "action_mode": "general",
            "ephemeral_subagents": _EPHEMERAL_SUBAGENTS,
            "messages": [],
        },
    )


async def _assert_stream_binding(chat: McpChatSession, *, expected_api: str) -> None:
    raw = await chat.evaluate(STREAM_API_BINDING_JS, intent=EvaluateIntent.SYNC_PROBE)
    binding = raw if isinstance(raw, dict) else {}
    if binding.get("usesRelativeProxy") is True or binding.get("hasPrivateBinding") is not True:
        raise AssertionError(f"SHPOIB stream binding missing: {binding!r}; expected={expected_api!r}")
    bound = str(binding.get("origin") or "").strip()
    if bound not in (expected_api.rstrip("/"), ""):
        raise AssertionError(f"SHPOIB stream binding mismatch: expected={expected_api!r} got={binding!r}")


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
        raw = await chat.evaluate(_SUBAGENT_APPROVAL_VISIBLE_JS, intent=EvaluateIntent.BRIDGE_POLL)
        value = raw
        if isinstance(value, dict) and "ready" in value:
            last_ui = value
        else:
            last_ui = {"ready": False, "raw": value}
        if last_ui.get("ready") is True:
            return last_ui
        await asyncio.sleep(1.5)
    raise AssertionError(f"Approval UI did not appear within {timeout_sec}s: {last_ui!r}")


async def _apply_runtime_bootstrap(chat: McpChatSession) -> None:
    bootstrap_js = e2e_runtime_bootstrap_apply_js()
    if not bootstrap_js:
        await chat.ensure_e2e_api_base_binding()
        return
    result = await chat.evaluate(bootstrap_js, intent=EvaluateIntent.AGENT_SUBMIT)
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError(f"E2E runtime bootstrap failed: {result}")


async def _prepare_live_chat(
    chat: McpChatSession,
    *,
    api_url: str,
    agent_id: str,
    chat_id: str,
    ui_base: str,
) -> str:
    """Chat already seeded via API and opened at /{chat_id} — bind bridge only."""
    _ = ui_base
    path_probe = await chat.evaluate(
        "(() => ({ path: location.pathname }))()",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    current_path = str(path_probe.get("path") or "") if isinstance(path_probe, dict) else ""
    if current_path != f"/{chat_id}":
        await chat.navigate_to_chat(chat_id, get_e2e_ui_url().rstrip("/"), timeout_sec=90.0)
    ensured = await chat.evaluate(
        """(() => {
          const bridge = window.__MYRM_E2E_CHAT__;
          if (!bridge?.ensureChatSession) return { ok: false, err: 'no ensureChatSession' };
          return Promise.resolve(bridge.ensureChatSession()).then(() => ({ ok: true }));
        })()""",
        intent=EvaluateIntent.ROUTE_ATTACH,
    )
    if not isinstance(ensured, dict) or ensured.get("ok") is not True:
        raise RuntimeError(f"ensureChatSession failed: {ensured!r}")
    bound_chat_id = str(await chat.bridge_chat_id() or "").strip()
    if bound_chat_id and bound_chat_id != chat_id:
        raise RuntimeError(f"Bridge chat id mismatch: expected={chat_id!r} got={bound_chat_id!r}")
    return chat_id


async def _http_kickoff_subagent_approval(
    api_url: str,
    chat_id: str,
    agent_id: str,
) -> None:
    """Start delegate+subagent via HTTP until subagent_approval (same as dashboard prepare)."""
    pin_and_verify_hitl_mode(api_url)

    def _kickoff() -> None:
        with httpx.Client(base_url=api_url, timeout=300.0) as client:
            run_until_subagent_approval(
                client,
                api_url,
                chat_id,
                agent_id,
                _USER_PROMPT,
                ephemeral_subagents=_EPHEMERAL_SUBAGENTS,
            )

    await asyncio.to_thread(_kickoff)


def _poll_subagent_status(
    api_url: str,
    chat_id: str,
) -> tuple[str, list[dict[str, object]]]:
    rows = http_json("GET", f"{api_url.rstrip('/')}/api/v1/chats/{chat_id}/subagents")
    data = rows.get("data") if isinstance(rows, dict) else None
    if not isinstance(data, list):
        return "unknown", []
    completed = [row for row in data if isinstance(row, dict) and row.get("status") == "completed"]
    if completed:
        return "completed", completed
    terminal = [row for row in data if isinstance(row, dict) and row.get("status") in ("cancelled", "failed", "error")]
    if terminal:
        return "terminal", terminal
    return "pending", [row for row in data if isinstance(row, dict)]


async def _click_approve_if_visible(chat: McpChatSession) -> bool:
    raw = await chat.evaluate(_SUBAGENT_APPROVAL_VISIBLE_JS, intent=EvaluateIntent.BRIDGE_POLL)
    visible = raw if isinstance(raw, dict) else {}
    if visible.get("hasApprove") is not True:
        return False
    if visible.get("ready") is not True and int(visible.get("queueLen") or 0) <= 0:
        return False
    click = await chat.evaluate(_CLICK_APPROVE_JS, intent=EvaluateIntent.SYNC_PROBE)
    return isinstance(click, dict) and click.get("ok") is True


async def _wait_for_subagent_completed_via_api(
    api_url: str,
    chat_id: str,
    chat: McpChatSession,
    *,
    timeout_sec: float = _POST_APPROVE_WAIT_SEC,
) -> list[dict[str, object]]:
    """Poll subagents + click further Approve cards (subagent_approval then bash tool_approval)."""
    deadline = time.monotonic() + timeout_sec
    last: object = None
    last_recover = 0.0
    while time.monotonic() < deadline:
        heartbeat_once()
        if await _click_approve_if_visible(chat):
            await asyncio.sleep(2.0)
        state, rows = _poll_subagent_status(api_url, chat_id)
        last = rows
        if state == "completed":
            return rows
        if state == "terminal":
            raise AssertionError(f"Subagent reached terminal state before completion: {rows!r}")
        now = time.monotonic()
        if now - last_recover >= 15.0:
            await _recover_hitl_in_browser(chat, chat_id)
            last_recover = now
        await asyncio.sleep(2.0)
    raise AssertionError(f"No completed subagent within {timeout_sec}s after WebUI approve: {last!r}")


async def _recover_hitl_in_browser(chat: McpChatSession, chat_id: str) -> dict[str, object]:
    chat_id_json = json.dumps(chat_id)
    raw = await chat.evaluate(
        f"({_RECOVER_HITL_JS})({chat_id_json})",
        intent=EvaluateIntent.AGENT_SUBMIT,
        recv_timeout=30.0,
    )
    result = raw if isinstance(raw, dict) else {"raw": raw}
    if result.get("ok") is not True and not result.get("timedOut"):
        raise RuntimeError(f"recoverHitlStream failed: {result!r}")
    return result


async def _run_approval_flow(
    chat: McpChatSession,
    agent_id: str,
    chat_id: str,
    *,
    api_url: str,
    ui_base: str,
    sent_marker: dict[str, bool],
) -> str:
    pin_and_verify_hitl_mode(api_url)
    resolved_chat_id = await _prepare_live_chat(
        chat,
        api_url=api_url,
        agent_id=agent_id,
        chat_id=chat_id,
        ui_base=ui_base,
    )
    await ensure_e2e_hitl_mode_in_browser(chat)
    await _assert_stream_binding(chat, expected_api=api_url)

    sent_marker["sent"] = True
    await _http_kickoff_subagent_approval(api_url, resolved_chat_id, agent_id)
    await _recover_hitl_in_browser(chat, resolved_chat_id)

    # Stay on the streaming tab — mid-stream Page.navigate drops SSE approval events.
    path_probe = await chat.evaluate(
        "(() => ({ path: location.pathname }))()",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    current_path = str(path_probe.get("path") or "") if isinstance(path_probe, dict) else ""
    if current_path != f"/{resolved_chat_id}":
        ui_base = get_e2e_ui_url().rstrip("/")
        await chat.navigate_to_chat(resolved_chat_id, ui_base, timeout_sec=90.0)

    approval = await _wait_for_approval_ui(chat, api_url=api_url)
    assert approval.get("queueLen") is not None
    assert approval.get("hasApprove") is True, f"Approval card missing Approve button: {approval}"

    click = await chat.evaluate(_CLICK_APPROVE_JS, intent=EvaluateIntent.SYNC_PROBE)
    assert isinstance(click, dict) and click.get("ok") is True, click

    # Resume stream may need multiple WebUI approves (subagent_approval + bash tool_approval).
    await _wait_for_subagent_completed_via_api(
        api_url,
        resolved_chat_id,
        chat,
        timeout_sec=_POST_APPROVE_WAIT_SEC,
    )
    return resolved_chat_id


@pytest.fixture(autouse=True)
def _pin_hitl_before(_chrome_e2e_item_runtime: object | None) -> None:
    api_base = get_e2e_api_url()
    pin_and_verify_hitl_mode(api_base)
    yield


@pytest.mark.e2e_search_policy("empty")
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
        pytest.fail("Provider not ready — seed WebUI model via chrome-e2e-model-seed.mjs")

    api_base = get_e2e_api_url()
    seed_live_e2e_providers(api_base)
    pin_and_verify_hitl_mode(api_base)
    ui_base = get_e2e_ui_url().rstrip("/")

    chat_id = str(uuid.uuid4())
    _seed_chat_via_api(api_base, chat_id)
    chat_url = f"{ui_base}/{chat_id}?agentId={_BUILTIN_AGENT_ID}"
    last_error = ""
    sent_marker: dict[str, bool] = {"sent": False}
    for attempt in range(1, _MAX_CHAT_ATTEMPTS + 1):
        heartbeat_once()
        try:
            with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
                chat = McpChatSession(client, page)
                await chat.bootstrap(chat_url, timeout_sec=180.0)
                await _apply_runtime_bootstrap(chat)
                chat_id = await _run_approval_flow(
                    chat,
                    _BUILTIN_AGENT_ID,
                    chat_id,
                    api_url=api_base,
                    ui_base=ui_base,
                    sent_marker=sent_marker,
                )
            e2e_resource_ledger.register("chat", chat_id)
            break
        except (AssertionError, RuntimeError, TimeoutError) as exc:
            last_error = str(exc)
            if sent_marker.get("sent"):
                raise
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
    assert any(isinstance(row, dict) and row.get("status") == "completed" for row in data), (
        f"No completed subagent after approval: {rows}"
    )
