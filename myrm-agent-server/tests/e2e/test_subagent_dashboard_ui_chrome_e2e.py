"""Real Chrome MCP E2E for subagent dashboard UI-injection + full front-end flow coverage.

Covers the scenarios the baseline dashboard E2E did not: sort reordering, stop-all
with confirmation dialog, teammate messages, live stream entries, overtime/stale
badges with dismiss, multi-level tree expand/collapse, completed/failed states,
header summary model mix, and a real user flow (WebUI send → LLM delegation →
running subagent → dashboard → front-end cancel).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from dev_gate_contract import MAX_PAGE_TIMEOUT_MS  # noqa: E402

from tests.e2e.test_subagent_dashboard_chrome_e2e import (
    _open_subagent_dashboard,
    _read_prepare_result,
)
from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    reload_mcp_page,
    wait_for_state,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger

_AGENT_ROOT = Path(__file__).resolve().parents[3]
_PREPARE_LIGHT = _AGENT_ROOT / "scripts/dev/subagent-dashboard-e2e-chat.mjs"
_PREPARE = _AGENT_ROOT / "scripts/dev/subagent-dashboard-e2e-prepare.mjs"

_DELEGATE_QUERY = (
    "请使用 delegate_task_tool 工具创建一个子智能体，必须将 agent_type 参数设置为 'bash_worker'，wait 设为 false。"
    "子智能体的任务：调用 bash_code_execute_tool 执行命令 `sleep 300`，关键要求：run_in_background 必须为 false（前台运行），"
    "timeout 参数必须显式设为 600，绝对禁止使用后台方式或 & 符号，必须等待命令完成后才能汇报结果并结束。"
    "注意：必须使用原生函数调用（Native Tool Calling / Function Calling）来调用工具，"
    "绝对不要在文本中输出 XML 格式的工具调用！"
)

# 与 scripts/dev/subagent-dashboard-e2e-prepare.mjs 的 E2E_BASH_EPHEMERAL 保持一致：
# 模拟用户在 WebUI 配置面板中启用了一个 bash 执行 worker 类型的 JIT 子智能体。
_E2E_BASH_EPHEMERAL = {
    "bash_worker": {
        "system_prompt": "You are a bash execution worker.",
        "tools": ["bash_code_execute_tool"],
    }
}


def _prepare_mjs_env(ledger: E2EResourceLedger) -> dict[str, str]:
    """Bind prepare scripts to the active chrome_e2e API (SHPOIB private pool SSOT)."""
    env = os.environ.copy()
    env["WAVE_LEDGER_LEASE_ID"] = ledger.lease_id
    env["WAVE_LEDGER_NAMESPACE"] = ledger.namespace
    env["E2E_API_BASE"] = get_e2e_api_url().rstrip("/")
    env["E2E_UI_BASE"] = get_e2e_ui_url().rstrip("/")
    return env


@pytest.fixture
def light_chat(e2e_resource_ledger: E2EResourceLedger) -> Iterator[dict[str, object]]:
    """Creates a fresh chat without spawning a real subagent (fast UI-injection scope)."""
    if shutil.which("bun") is None:
        pytest.skip("bun is required for subagent dashboard light chat")
    env = _prepare_mjs_env(e2e_resource_ledger)
    process = subprocess.Popen(
        ["bun", str(_PREPARE_LIGHT)],
        cwd=str(_AGENT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        yield _read_prepare_result(process, timeout_sec=60.0)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _type_chat_input_text(
    client: object,
    page: object,
    text: str,
    *,
    selector: str = "[data-chat-input]",
) -> dict[str, object]:
    """Fill the React-controlled chat textarea via native setter + input/change events.

    Mirrors a real user typing: CDP ``type_text`` is unreliable for React
    controlled inputs, so we set the value through the native value setter and
    dispatch the DOM events React listens to. Returns the resulting field value.
    """
    result = client.evaluate(
        page,
        f"""(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return {{ ok: false, err: 'input-not-found' }};
  const proto = window.HTMLTextAreaElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  if (!setter) return {{ ok: false, err: 'setter-not-found' }};
  setter.call(el, {json.dumps(text)});
  const len = el.value.length;
  el.setSelectionRange(len, len);
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return {{ ok: true, value: el.value }};
}})()""",
        timeout_sec=10.0,
    )
    assert isinstance(result, dict) and result.get("ok") is True, result
    return result


def _pin_direct_sse(client: object, page: object) -> None:
    """Pin SHPOIB direct-SSE so a real-UI send bypasses the workspace-multiplex bridge.

    Mirrors bridge.submitAndObserveTurn (E2EChatBridge.tsx), which auto-sets
    ``__MYRM_E2E_DIRECT_SSE__ = true`` before every bridge send. A plain UI send does
    not, so without this pin the agent-stream POST would wait up to 30s on the
    multiplex bridge (connectionManager.waitUntilReady) and, on timeout, the textarea
    would never clear because the store only clears it after the first SSE chunk
    (streamConsumer.ts setInputMessage('')).
    """
    pinned = client.evaluate(
        page,
        """(() => { window.__MYRM_E2E_DIRECT_SSE__ = true; return true; })()""",
        timeout_sec=10.0,
    )
    assert pinned is True, "Failed to pin __MYRM_E2E_DIRECT_SSE__"


def _real_send_chat_message(
    client: object,
    page: object,
    query: str,
) -> dict[str, object]:
    """Simulate a real user: type into [data-chat-input], click the send button,
    and confirm the textarea cleared (message committed into the send pipeline)."""
    input_seen = wait_for_state(
        client,
        page,
        """(() => ({
          ready: !!document.querySelector('[data-chat-input]'),
        }))()""",
        timeout_sec=30.0,
    )
    assert input_seen.get("ready") is True, "Chat input textarea missing"
    typed = _type_chat_input_text(client, page, query)
    assert typed.get("ok") is True, f"Type into chat input failed: {typed}"
    send_ready = wait_for_state(
        client,
        page,
        """(() => {
          const btn = document.querySelector('.message-send-btn');
          return {
            ready: !!btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true',
            disabled: btn?.disabled ?? null,
          };
        })()""",
        timeout_sec=30.0,
    )
    assert send_ready.get("ready") is True, f"Send button not ready: {send_ready}"
    clicked = client.evaluate(
        page,
        """(() => {
          const btn = document.querySelector('.message-send-btn');
          if (!btn || btn.disabled) return false;
          btn.click();
          return true;
        })()""",
        timeout_sec=5.0,
    )
    assert clicked is True, "Send button click failed"
    cleared = wait_for_state(
        client,
        page,
        """(() => {
          const el = document.querySelector('[data-chat-input]');
          return { ready: !!el && el.value === '' };
        })()""",
        timeout_sec=30.0,
    )
    if not cleared.get("ready"):
        diag = client.evaluate(
            page,
            """(() => {
              const turn = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? null;
              const provider = window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null;
              const el = document.querySelector('[data-chat-input]');
              const toasts = Array.from(
                document.querySelectorAll('[data-sonner-toast], .ant-message-notice, [role="alert"]'),
              )
                .map((node) => node.textContent?.trim()?.slice(0, 200))
                .filter(Boolean)
                .slice(0, 6);
              return {
                inputValue: el?.value?.slice(0, 120) ?? null,
                directSse: !!window.__MYRM_E2E_DIRECT_SSE__,
                turn,
                provider,
                toasts,
              };
            })()""",
            timeout_sec=10.0,
        )
        print("DIAG_SEND_CLEAR_FAILED=" + json.dumps(diag, default=str)[:1500])
    assert cleared.get("ready") is True, f"Chat input did not clear after send: {cleared}"
    eph_status = client.evaluate(
        page,
        """(() => {
          const status = window.__MYRM_E2E_CHAT__?.ephSubagentsStatus?.();
          return status ?? { hasConfig: null, ephKeys: null, applied: null, sendOpts: null };
        })()""",
        timeout_sec=10.0,
    )
    return {"ok": True, "eph_status": eph_status}


def _wait_subagent_status(
    chat_id: str,
    task_id: str,
    status: str,
    timeout_sec: float = 150.0,
) -> dict[str, object] | None:
    """Poll the subagents API until the given task_id reaches the target status."""
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] | None = None
    while time.monotonic() < deadline:
        payload = http_json(
            "GET", f"{get_e2e_api_url()}/api/v1/chats/{chat_id}/subagents"
        )
        last = payload if isinstance(payload, dict) else None
        data = last.get("data") if last else None
        if isinstance(data, list):
            for row in data:
                if (
                    isinstance(row, dict)
                    and row.get("task_id") == task_id
                    and row.get("status") == status
                ):
                    return row
        time.sleep(2.0)
    return last


def _open_dashboard_seeded(client, page, chat_id: str, rows: list[dict[str, object]]) -> None:
    _open_subagent_dashboard(client, page, chat_id, fallback_rows=rows)
    seeded = client.evaluate(
        page,
        f"""(() => {{
          const store = window.__myrmSubagentStore?.getState?.();
          if (!store?.setNodes) return false;
          store.setNodes({json.dumps(rows)});
          return true;
        }})()""",
        timeout_sec=10.0,
    )
    assert seeded is True, "Store seed via bridge failed"


def _wait_running_row(chat_id: str, timeout_sec: float = 240.0) -> dict[str, object]:
    """Poll the subagents API until a running row appears for a freshly spawned agent."""
    deadline = time.monotonic() + timeout_sec
    last: object = {}
    while time.monotonic() < deadline:
        payload = http_json(
            "GET", f"{get_e2e_api_url()}/api/v1/chats/{chat_id}/subagents"
        )
        last = payload
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict) and row.get("status") == "running":
                    return row
        time.sleep(2.0)
    raise AssertionError(f"No running subagent spawned for chat {chat_id}: {last!r}")


def _tree_order_expr() -> str:
    return """(() => {
      const ids = Array.from(document.querySelectorAll('[data-subagent-tree-id]'))
        .map((el) => el.getAttribute('data-subagent-tree-id'));
      return { ready: ids.length > 0, ids };
    })()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_sort_reorders_tree(light_chat: dict[str, object]) -> None:
    """Sort controls reorder the tree (busiest / slowest / status)."""
    chat_id = str(light_chat.get("chatId") or "")
    assert chat_id
    ui_url = str(light_chat.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    rows: list[dict[str, object]] = [
        {
            "task_id": "sort-a",
            "parent_task_id": "",
            "status": "failed",
            "agent_type": "research",
            "description": "Sort A failed",
            "duration_seconds": 30,
            "token_usage": {"total_cost_usd": 0.9, "total_tokens": 9000},
        },
        {
            "task_id": "sort-b",
            "parent_task_id": "",
            "status": "completed",
            "agent_type": "review",
            "description": "Sort B completed",
            "duration_seconds": 500,
            "token_usage": {"total_cost_usd": 0.1, "total_tokens": 1000},
        },
        {
            "task_id": "sort-c",
            "parent_task_id": "",
            "status": "running",
            "agent_type": "bash_worker",
            "description": "Sort C running",
            "duration_seconds": 60,
            "token_usage": {"total_cost_usd": 0.5, "total_tokens": 5000},
        },
    ]
    expected: dict[str, list[str]] = {
        "spawn": ["sort-a", "sort-b", "sort-c"],
        "busiest": ["sort-a", "sort-c", "sort-b"],
        "slowest": ["sort-b", "sort-c", "sort-a"],
        "status": ["sort-a", "sort-c", "sort-b"],
    }
    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_dashboard_seeded(client, page, chat_id, rows)
        for sort_value, ids in expected.items():
            clicked = client.evaluate(
                page,
                f"""(() => {{
                  const btn = document.querySelector('[data-testid="subagent-sort-{sort_value}"]');
                  if (!btn) return false;
                  btn.click();
                  return true;
                }})()""",
                timeout_sec=5.0,
            )
            assert clicked is True, f"Sort button missing: {sort_value}"
            order = wait_for_state(
                client,
                page,
                f"""(() => {{
                  const result = {_tree_order_expr()};
                  const expected = {json.dumps(ids)};
                  return {{ ready: result.ids.length === expected.length && result.ids.join(',') === expected.join(','), ids: result.ids }};
                }})()""",
                timeout_sec=15.0,
            )
            assert order.get("ready") is True, (
                f"Sort {sort_value} expected {ids} got {order}"
            )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_stop_all_confirms_and_cancels(
    light_chat: dict[str, object],
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Stop-all opens the confirm dialog and cancels every running subagent via API.

    The UI is opened and attached first; the real subagent is spawned afterwards
    through the agent-stream delegate path, so the cancel window never competes
    with UI cold-start latency (bash foreground execution defaults to a 60s
    timeout, which would otherwise terminate the spawned agent too early).
    """
    chat_id = str(light_chat.get("chatId") or "")
    assert chat_id
    ui_url = str(light_chat.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    placeholder_row: dict[str, object] = {
        "task_id": "stop-all-placeholder",
        "parent_task_id": "",
        "status": "running",
        "agent_type": "bash_worker",
        "description": "Stop All Placeholder",
        "startedAt": int(time.time() * 1000) - 5_000,
    }

    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_subagent_dashboard(
            client, page, chat_id, fallback_rows=[placeholder_row]
        )

        spawn_env = _prepare_mjs_env(e2e_resource_ledger)
        spawn_env["E2E_HOLD_MS"] = "600000"
        spawn = subprocess.Popen(
            ["bun", str(_PREPARE), f"--chat={chat_id}"],
            cwd=str(_AGENT_ROOT),
            env=spawn_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            task_row = _wait_running_row(chat_id, timeout_sec=240.0)
            task_id = str(task_row.get("task_id") or "")
            assert task_id, f"Spawned subagent missing task_id: {task_row}"
            print("DIAG_TASK_ROW=" + json.dumps(task_row, default=str)[:800])
            rows: list[dict[str, object]] = [task_row]
            rows.append(
                {
                    "task_id": "stop-all-beta",
                    "parent_task_id": "",
                    "status": "running",
                    "agent_type": "bash_worker",
                    "description": "Stop All Beta",
                    "startedAt": int(time.time() * 1000) - 5_000,
                }
            )
            seeded = client.evaluate(
                page,
                f"""(() => {{
                  const store = window.__myrmSubagentStore?.getState?.();
                  if (!store?.setNodes) return false;
                  store.setNodes({json.dumps(rows)});
                  return true;
                }})()""",
                timeout_sec=10.0,
            )
            assert seeded is True, "Store seed via bridge failed"
            stop_all = wait_for_state(
                client,
                page,
                """(() => {
                  const btn = document.querySelector('[data-testid="subagent-stop-all-btn"]');
                  return { ready: !!btn, hasBtn: !!btn };
                })()""",
                timeout_sec=30.0,
            )
            assert stop_all.get("hasBtn") is True, f"Stop-all button missing: {stop_all}"
            clicked = client.evaluate(
                page,
                """(() => {
                  const btn = document.querySelector('[data-testid="subagent-stop-all-btn"]');
                  if (!btn) return false;
                  btn.click();
                  return true;
                })()""",
                timeout_sec=5.0,
            )
            assert clicked is True
            dialog = wait_for_state(
                client,
                page,
                """(() => {
                  const dlg = document.querySelector('[role="alertdialog"]');
                  return { ready: !!dlg, hasDialog: !!dlg };
                })()""",
                timeout_sec=15.0,
            )
            assert dialog.get("hasDialog") is True, f"Stop-all confirm dialog missing: {dialog}"
            confirmed = client.evaluate(
                page,
                """(() => {
                  const buttons = Array.from(document.querySelectorAll('[role="alertdialog"] button'));
                  const confirmBtn = buttons[buttons.length - 1];
                  if (!confirmBtn) return false;
                  confirmBtn.click();
                  return true;
                })()""",
                timeout_sec=5.0,
            )
            assert confirmed is True
            cancelled = wait_for_state(
                client,
                page,
                """(() => {
                  const store = window.__myrmSubagentStore?.getState?.();
                  if (!store) return { ready: false, reason: 'store missing' };
                  const nodes = store.nodes ?? {};
                  const all = Object.values(nodes);
                  return {
                    ready: all.length > 0 && all.every((n) => n.status === 'cancelled'),
                    statuses: all.map((n) => n.status),
                  };
                })()""",
                timeout_sec=30.0,
            )
            assert (
                cancelled.get("ready") is True
            ), f"Stop-all did not cancel all running nodes: {cancelled}"
            api_payload = http_json(
                "GET", f"{get_e2e_api_url()}/api/v1/chats/{chat_id}/subagents"
            )
            data = api_payload.get("data") if isinstance(api_payload, dict) else None
            rows_after = [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
            deadline_cancel = time.monotonic() + 90.0
            while time.monotonic() < deadline_cancel and any(
                row.get("status") == "running" for row in rows_after
            ):
                time.sleep(3.0)
                api_payload = http_json(
                    "GET", f"{get_e2e_api_url()}/api/v1/chats/{chat_id}/subagents"
                )
                data = api_payload.get("data") if isinstance(api_payload, dict) else None
                rows_after = [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
            running_after = [row for row in rows_after if row.get("status") == "running"]
            assert (
                not running_after
            ), f"Real subagent still running after stop-all: {running_after}"
        finally:
            if spawn.poll() is None:
                spawn.terminate()
                try:
                    spawn.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    spawn.kill()
                    spawn.wait(timeout=5)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_teammate_messages_render(
    light_chat: dict[str, object],
) -> None:
    """Teammate messages appear under the subagent tree row."""
    chat_id = str(light_chat.get("chatId") or "")
    assert chat_id
    ui_url = str(light_chat.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    now = int(time.time() * 1000)
    rows: list[dict[str, object]] = [
        {
            "task_id": "mate-a",
            "parent_task_id": "",
            "status": "running",
            "agent_type": "research",
            "description": "Mate Alpha",
            "startedAt": now - 10_000,
            "teammate_messages": [
                {
                    "message_id": "m1",
                    "from_task_id": "mate-b",
                    "to_task_id": "mate-a",
                    "body": "E2E teammate ping from B",
                    "created_at": now - 5_000,
                },
                {
                    "message_id": "m2",
                    "from_task_id": "mate-a",
                    "to_task_id": "mate-b",
                    "body": "E2E teammate ack from A",
                    "created_at": now - 3_000,
                },
            ],
        },
        {
            "task_id": "mate-b",
            "parent_task_id": "",
            "status": "running",
            "agent_type": "bash_worker",
            "description": "Mate Beta",
            "startedAt": now - 10_000,
        },
    ]
    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_dashboard_seeded(client, page, chat_id, rows)
        rendered = wait_for_state(
            client,
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const text = panel?.textContent || '';
              return {
                ready: /E2E teammate ping from B/.test(text) && /E2E teammate ack from A/.test(text),
                text: text.slice(0, 600),
              };
            })()""",
            timeout_sec=30.0,
        )
        assert rendered.get("ready") is True, f"Teammate messages not rendered: {rendered}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_stream_entries_render(
    light_chat: dict[str, object],
) -> None:
    """Live stream entries (tool/progress/error) render under the running node."""
    chat_id = str(light_chat.get("chatId") or "")
    assert chat_id
    ui_url = str(light_chat.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    now = int(time.time() * 1000)
    rows: list[dict[str, object]] = [
        {
            "task_id": "stream-a",
            "parent_task_id": "",
            "status": "running",
            "agent_type": "bash_worker",
            "description": "Stream Alpha",
            "startedAt": now - 10_000,
            "stream": [
                {"kind": "tool", "text": "bash_code_execute_tool", "timestamp": now - 4_000, "durationMs": 1200},
                {"kind": "progress", "text": "E2E progress line", "timestamp": now - 3_000},
                {"kind": "thinking", "text": "E2E thinking line", "timestamp": now - 2_000},
                {"kind": "error", "text": "E2E error line", "timestamp": now - 1_000, "isError": True},
            ],
        }
    ]
    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_dashboard_seeded(client, page, chat_id, rows)
        rendered = wait_for_state(
            client,
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const text = panel?.textContent || '';
              return {
                ready: /bash_code_execute_tool/.test(text)
                  && /E2E progress line/.test(text)
                  && /E2E thinking line/.test(text)
                  && /E2E error line/.test(text),
                text: text.slice(0, 600),
              };
            })()""",
            timeout_sec=30.0,
        )
        assert rendered.get("ready") is True, f"Stream entries not rendered: {rendered}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_overtime_stale_badges_dismiss(
    light_chat: dict[str, object],
) -> None:
    """Overtime (amber) and stale (red) banners render and dismiss correctly."""
    chat_id = str(light_chat.get("chatId") or "")
    assert chat_id
    ui_url = str(light_chat.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    now = int(time.time() * 1000)
    rows: list[dict[str, object]] = [
        {
            "task_id": "slow-a",
            "parent_task_id": "",
            "status": "running",
            "agent_type": "research",
            "description": "Slow Alpha",
            "startedAt": now - 180_000,
            "progress": 5,
        },
        {
            "task_id": "stale-b",
            "parent_task_id": "",
            "status": "running",
            "agent_type": "bash_worker",
            "description": "Stale Beta",
            "startedAt": now - 60_000,
            "stale": True,
            "staleDurationSeconds": 600,
            "wastedTokens": 5000,
        },
    ]
    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_dashboard_seeded(client, page, chat_id, rows)
        banners = wait_for_state(
            client,
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const amber = panel?.querySelector('[class~="bg-amber-50"]');
              const red = panel?.querySelector('[class~="bg-red-50"]');
              return { ready: !!amber && !!red, hasAmber: !!amber, hasRed: !!red };
            })()""",
            timeout_sec=30.0,
        )
        assert banners.get("hasAmber") is True, f"Overtime banner missing: {banners}"
        assert banners.get("hasRed") is True, f"Stale banner missing: {banners}"
        dismissed = client.evaluate(
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const buttons = panel ? Array.from(panel.querySelectorAll('[class~="bg-amber-50"] > button, [class~="bg-red-50"] > button')) : [];
              if (buttons.length < 2) return false;
              buttons[0].click();
              buttons[1].click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert dismissed is True, "Dismiss buttons not found"
        gone = wait_for_state(
            client,
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const amber = panel?.querySelector('[class~="bg-amber-50"]');
              const red = panel?.querySelector('[class~="bg-red-50"]');
              return { ready: !amber && !red };
            })()""",
            timeout_sec=15.0,
        )
        assert gone.get("ready") is True, f"Badges did not dismiss: {gone}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_tree_expand_collapse_children(
    light_chat: dict[str, object],
) -> None:
    """Multi-level tree children collapse and expand via the chevron toggle."""
    chat_id = str(light_chat.get("chatId") or "")
    assert chat_id
    ui_url = str(light_chat.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    rows: list[dict[str, object]] = [
        {
            "task_id": "parent-1",
            "parent_task_id": "",
            "status": "running",
            "agent_type": "orchestrator",
            "description": "Parent One",
        },
        {
            "task_id": "child-1",
            "parent_task_id": "parent-1",
            "status": "running",
            "agent_type": "research",
            "description": "Child One",
        },
        {
            "task_id": "child-2",
            "parent_task_id": "parent-1",
            "status": "completed",
            "agent_type": "review",
            "description": "Child Two",
        },
    ]
    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_dashboard_seeded(client, page, chat_id, rows)
        expanded = wait_for_state(
            client,
            page,
            """(() => {
              const ids = Array.from(document.querySelectorAll('[data-subagent-tree-id]'))
                .map((el) => el.getAttribute('data-subagent-tree-id'));
              const parent = document.querySelector('[data-subagent-tree-id="parent-1"]');
              return { ready: ids.length === 3 && !!parent, ids };
            })()""",
            timeout_sec=30.0,
        )
        assert expanded.get("ready") is True, f"Children not expanded by default: {expanded}"
        collapsed = client.evaluate(
            page,
            """(() => {
              const parent = document.querySelector('[data-subagent-tree-id="parent-1"]');
              const toggle = parent?.querySelector('button');
              if (!toggle) return false;
              toggle.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert collapsed is True, "Expand toggle missing"
        hidden = wait_for_state(
            client,
            page,
            """(() => {
              const ids = Array.from(document.querySelectorAll('[data-subagent-tree-id]'))
                .map((el) => el.getAttribute('data-subagent-tree-id'));
              return {
                ready: ids.length === 1 && ids[0] === 'parent-1',
                ids,
              };
            })()""",
            timeout_sec=15.0,
        )
        assert hidden.get("ready") is True, f"Collapse did not hide children: {hidden}"
        reexpanded = client.evaluate(
            page,
            """(() => {
              const parent = document.querySelector('[data-subagent-tree-id="parent-1"]');
              const toggle = parent?.querySelector('button');
              if (!toggle) return false;
              toggle.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert reexpanded is True
        restored = wait_for_state(
            client,
            page,
            """(() => {
              const ids = Array.from(document.querySelectorAll('[data-subagent-tree-id]'))
                .map((el) => el.getAttribute('data-subagent-tree-id'));
              return { ready: ids.length === 3, ids };
            })()""",
            timeout_sec=15.0,
        )
        assert restored.get("ready") is True, f"Expand did not restore children: {restored}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_completed_failed_states_and_header_summary(
    light_chat: dict[str, object],
) -> None:
    """Completed/failed/timed_out/cancelled states render; header shows model mix."""
    chat_id = str(light_chat.get("chatId") or "")
    assert chat_id
    ui_url = str(light_chat.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    rows: list[dict[str, object]] = [
        {
            "task_id": "st-completed",
            "parent_task_id": "",
            "status": "completed",
            "agent_type": "research",
            "description": "State Completed",
            "effective_model": "agnes-2.5-flash",
        },
        {
            "task_id": "st-failed",
            "parent_task_id": "",
            "status": "failed",
            "agent_type": "bash_worker",
            "description": "State Failed",
            "error": "boom",
            "effective_model": "agnes-2.5-flash",
        },
        {
            "task_id": "st-timed",
            "parent_task_id": "",
            "status": "timed_out",
            "agent_type": "review",
            "description": "State Timed",
        },
        {
            "task_id": "st-cancelled",
            "parent_task_id": "",
            "status": "cancelled",
            "agent_type": "research",
            "description": "State Cancelled",
        },
    ]
    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_dashboard_seeded(client, page, chat_id, rows)
        rendered = wait_for_state(
            client,
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const text = panel?.textContent || '';
              const iconClasses = Array.from(panel?.querySelectorAll('svg') ?? [])
                .map((svg) => svg.getAttribute('class') || '');
              return {
                ready: /State Completed/.test(text)
                  && /State Failed/.test(text)
                  && /State Timed/.test(text)
                  && /State Cancelled/.test(text)
                  && /agnes-2.5-flash/.test(text),
                text: text.slice(0, 800),
                hasGreenCheck: iconClasses.some((c) => /text-green-500/.test(c)),
                hasRedX: iconClasses.some((c) => /text-red-500/.test(c)),
              };
            })()""",
            timeout_sec=30.0,
        )
        assert rendered.get("ready") is True, f"State nodes not rendered: {rendered}"
        assert rendered.get("hasGreenCheck") is True, f"Completed icon missing: {rendered}"
        assert rendered.get("hasRedX") is True, f"Failed icon missing: {rendered}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(540)
def test_subagent_dashboard_frontend_full_flow_delegation_and_cancel(
    light_chat: dict[str, object],
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real user flow: WebUI chat page send → LLM delegation → running subagent → dashboard → cancel.

    Single-page flow: the chat is created first, the chat route is opened and attached,
    then the delegate message is sent inside that page. The SSE stream stays held by the
    page (no navigation that would disconnect it), and the subagent dashboard renders its
    trigger automatically via its own 2s fetchSubagents poll once a running row appears.
    """
    if (
        not os.environ.get("BASIC_API_KEY", "").strip()
        or not os.environ.get("BASIC_MODEL", "").strip()
    ):
        pytest.skip("BASIC_API_KEY and BASIC_MODEL are required")
    chat_id = str(light_chat.get("chatId") or "")
    assert chat_id
    ui_url = str(light_chat.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    # PRIVATE backends start with an empty securityConfig; delegate_task_tool then
    # requires HITL approval which no one approves in an automated WebUI flow and it
    # auto-denies on timeout. Seed YOLO (like subagent-dashboard-e2e-prepare.mjs does
    # for the API-level tests) so the real WebUI send can delegate without approval.
    seed_env = _prepare_mjs_env(e2e_resource_ledger)
    seed = subprocess.Popen(
        ["bun", str(_PREPARE), "--seed-config-only"],
        cwd=str(_AGENT_ROOT),
        env=seed_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        seed_result = _read_prepare_result(seed, timeout_sec=90.0)
        assert seed_result.get("seeded") is True, f"Config seed failed: {seed_result}"
        _run_full_flow_body(chat_id, ui_url)
    finally:
        if seed.poll() is None:
            seed.terminate()
            try:
                seed.wait(timeout=5)
            except subprocess.TimeoutExpired:
                seed.kill()
                seed.wait(timeout=5)


def _run_full_flow_body(chat_id: str, ui_url: str) -> None:
    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        wait_for_state(
            client,
            page,
            """(() => ({
              ready: !!window.__MYRM_E2E_CHAT__?.sendChatMessage && !!window.__MYRM_E2E_SUBAGENT__?.hydrate,
            }))()""",
            timeout_sec=30.0,
        )
        _pin_direct_sse(client, page)
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
        assert attach_result.get("ready") is True, f"attachToChat failed: {attach_result}"
        sent = _real_send_chat_message(client, page, _DELEGATE_QUERY)
        assert sent.get("ok") is True, f"Real chat send failed: {sent}"
        eph_status = sent.get("eph_status")
        # 真实用户路径：agentConfig 未注入 ephemeral（发送 payload 不含 ephemeral_subagents），
        # 后端 converter.py 在 request 无 ephemeral 时回退 chat.ephemeral_subagents，
        # 因此下方委派能跑起来本身即是 chat 级回退生效的证据。
        print("DIAG_EPH_STATUS_REAL_SEND=" + json.dumps(eph_status, default=str))

        task_id: str | None = None
        deadline = time.monotonic() + 300.0
        last_payload: object = None
        while time.monotonic() < deadline:
            payload = http_json(
                "GET", f"{get_e2e_api_url()}/api/v1/chats/{chat_id}/subagents"
            )
            last_payload = payload
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, list):
                running = [
                    row
                    for row in data
                    if isinstance(row, dict) and row.get("status") == "running"
                ]
                if running:
                    task_id = str(running[0].get("task_id") or "")
                    break
            time.sleep(2.0)
        assert task_id, (
            f"No running subagent after front-end send: {last_payload!r} "
            f"eph_status={eph_status!r} sent={sent!r}"
        )
        api_snapshot = http_json(
            "GET", f"{get_e2e_api_url()}/api/v1/chats/{chat_id}/subagents"
        )
        print("DIAG_SUBAGENTS_AFTER_SEND=" + json.dumps(api_snapshot, default=str)[:800])

        # 真实场景：用户切走/刷新页面后重新回到 chat，dashboard 必须通过前端的
        # fetchSubagents 轮询（无任何 store 注入）从 API 恢复出 running 子agent，
        # 之后在同一页面完成 cancel 闭环。
        reload_mcp_page(client, page, target_url=ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS)
        reattached = wait_for_state(
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
            timeout_sec=120.0,
        )
        assert reattached.get("ready") is True, f"Re-attach after reload failed: {reattached}"
        _pin_direct_sse(client, page)
        restored = wait_for_state(
            client,
            page,
            """(() => {
              const button = document.querySelector('[data-testid="subagent-dashboard-trigger"]');
              const store = window.__myrmSubagentStore?.getState?.();
              const nodes = store?.nodes ?? {};
              const runningNodes = Object.values(nodes).filter((n) => n?.status === 'running').length;
              return {
                ready: !!button && runningNodes > 0,
                nodeCount: Object.keys(nodes).length,
                runningNodes,
              };
            })()""",
            timeout_sec=120.0,
        )
        assert restored.get("ready") is True, (
            f"Dashboard did not restore running subagent after reload: {restored}"
        )
        # 点击展开 panel（Sheet 内容默认未挂载），cancel 按钮才可见。
        trigger_seen = wait_for_state(
            client,
            page,
            """(() => {
              const button = document.querySelector('[data-testid="subagent-dashboard-trigger"]');
              const store = window.__myrmSubagentStore?.getState?.();
              return {
                ready: !!button,
                nodeCount: store ? Object.keys(store.nodes ?? {}).length : null,
              };
            })()""",
            timeout_sec=90.0,
        )
        assert trigger_seen.get("ready") is True, f"Dashboard trigger missing after reload: {trigger_seen}"
        opened = client.evaluate(
            page,
            """(() => {
              const button = document.querySelector('[data-testid="subagent-dashboard-trigger"]');
              if (!button) return false;
              button.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert opened is True, "Dashboard trigger click failed"
        panel_seen = wait_for_state(
            client,
            page,
            """(() => ({
              ready: !!document.querySelector('[data-testid="subagent-dashboard-panel"]'),
            }))()""",
            timeout_sec=30.0,
        )
        assert panel_seen.get("ready") is True, "Dashboard panel did not open"

        row = wait_for_state(
            client,
            page,
            f"""(() => {{
              const cancel = document.querySelector('[data-testid="subagent-cancel-btn"][data-task-id="{task_id}"]')
                || document.querySelector('[data-testid="subagent-cancel-btn"]');
              const panelText = document.querySelector('[data-testid="subagent-dashboard-panel"]')?.textContent || '';
              const store = window.__myrmSubagentStore?.getState?.();
              return {{
                ready: !!cancel,
                hasCancel: !!cancel,
                hasSleep: /sleep/i.test(panelText) || /bash/i.test(panelText),
                nodeCount: store ? Object.keys(store.nodes ?? {{}}).length : null,
              }};
            }})()""",
            timeout_sec=120.0,
        )
        assert row.get("hasCancel") is True, f"Cancel button missing: {row}"
        opened = client.evaluate(
            page,
            f"""(() => {{
              const button = document.querySelector('[data-testid="subagent-cancel-btn"][data-task-id="{task_id}"]')
                || document.querySelector('[data-testid="subagent-cancel-btn"]');
              if (!button) return false;
              button.click();
              return true;
            }})()""",
            timeout_sec=5.0,
        )
        assert opened is True, "Cancel button click failed"
        dialog = wait_for_state(
            client,
            page,
            """(() => {
              const dlg = document.querySelector('[role="alertdialog"]');
              return { ready: !!dlg };
            })()""",
            timeout_sec=15.0,
        )
        assert dialog.get("ready") is True, "Cancel confirm dialog missing"
        confirmed = client.evaluate(
            page,
            """(() => {
              const buttons = Array.from(document.querySelectorAll('[role="alertdialog"] button'));
              const confirmBtn = buttons[buttons.length - 1];
              if (!confirmBtn) return false;
              confirmBtn.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert confirmed is True
        verified = wait_for_state(
            client,
            page,
            f"""(async () => {{
              const apiBase = window.__MYRM_E2E_API_BASE__ || '';
              const url = `${{apiBase}}/api/v1/chats/{chat_id}/subagents/{task_id}/cancel`;
              const response = await fetch(url, {{ method: 'POST', credentials: 'include' }});
              return {{ ready: response.status === 404, status: response.status }};
            }})()""",
            timeout_sec=60.0,
        )
        assert verified.get("status") == 404
        store_status = wait_for_state(
            client,
            page,
            f"""(() => {{
              const store = window.__myrmSubagentStore?.getState?.();
              const node = store?.nodes?.[{json.dumps(task_id)}];
              return {{ ready: !!node && node.status === 'cancelled', status: node?.status ?? null }};
            }})()""",
            timeout_sec=30.0,
        )
        assert (
            store_status.get("ready") is True
        ), f"Store did not mark cancelled: {store_status}"


# 自然完成场景：委派一个 sleep 3 的短任务，子agent 自己跑完后进入 completed，
# dashboard 无需任何 store 注入即可渲染 completed 节点。
_COMPLETE_QUERY = (
    "请使用 delegate_task_tool 工具创建一个子智能体，必须将 agent_type 参数设置为 'bash_worker'。"
    "子智能体的任务：调用 bash_code_execute_tool 工具执行命令 `sleep 3`。关键要求：run_in_background 必须为 false（前台运行），"
    "timeout 参数必须显式设为 120。命令执行完成后立即汇报结果并结束任务。"
    "注意：必须使用原生函数调用（Native Tool Calling / Function Calling）来调用工具，"
    "绝对不要在文本中输出 XML 格式的工具调用！"
)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(540)
def test_subagent_dashboard_frontend_subagent_completes_flow_chrome_e2e(
    light_chat: dict[str, object],
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real user flow: short delegation via the chat textarea, the subagent finishes
    by itself (bash `sleep 3`), and the dashboard renders the completed node from the
    API without any store injection.
    """
    if (
        not os.environ.get("BASIC_API_KEY", "").strip()
        or not os.environ.get("BASIC_MODEL", "").strip()
    ):
        pytest.skip("BASIC_API_KEY and BASIC_MODEL are required")
    chat_id = str(light_chat.get("chatId") or "")
    assert chat_id
    ui_url = str(light_chat.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    seed_env = _prepare_mjs_env(e2e_resource_ledger)
    seed = subprocess.Popen(
        ["bun", str(_PREPARE), "--seed-config-only"],
        cwd=str(_AGENT_ROOT),
        env=seed_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        seed_result = _read_prepare_result(seed, timeout_sec=90.0)
        assert seed_result.get("seeded") is True, f"Config seed failed: {seed_result}"
        _run_completed_flow_body(chat_id, ui_url)
    finally:
        if seed.poll() is None:
            seed.terminate()
            try:
                seed.wait(timeout=5)
            except subprocess.TimeoutExpired:
                seed.kill()
                seed.wait(timeout=5)


def _run_completed_flow_body(chat_id: str, ui_url: str) -> None:
    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        wait_for_state(
            client,
            page,
            """(() => ({
              ready: !!window.__MYRM_E2E_CHAT__?.sendChatMessage && !!window.__MYRM_E2E_SUBAGENT__?.hydrate,
            }))()""",
            timeout_sec=30.0,
        )
        _pin_direct_sse(client, page)
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
        assert attach_result.get("ready") is True, f"attachToChat failed: {attach_result}"
        sent = _real_send_chat_message(client, page, _COMPLETE_QUERY)
        assert sent.get("ok") is True, f"Real chat send failed: {sent}"

        task_id: str | None = None
        deadline = time.monotonic() + 300.0
        last_payload: object = None
        while time.monotonic() < deadline:
            payload = http_json(
                "GET", f"{get_e2e_api_url()}/api/v1/chats/{chat_id}/subagents"
            )
            last_payload = payload
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, list):
                running = [
                    row
                    for row in data
                    if isinstance(row, dict) and row.get("status") == "running"
                ]
                if running:
                    task_id = str(running[0].get("task_id") or "")
                    break
            time.sleep(2.0)
        assert task_id, f"No running subagent after real send: {last_payload!r}"

        completed_row = _wait_subagent_status(chat_id, task_id, "completed", timeout_sec=180.0)
        assert completed_row is not None, (
            f"Subagent {task_id} did not reach completed: {completed_row!r}"
        )
        print("DIAG_COMPLETED_ROW=" + json.dumps(completed_row, default=str)[:600])

        trigger_seen = wait_for_state(
            client,
            page,
            """(() => {
              const button = document.querySelector('[data-testid="subagent-dashboard-trigger"]');
              const store = window.__myrmSubagentStore?.getState?.();
              return {
                ready: !!button,
                nodeCount: store ? Object.keys(store.nodes ?? {}).length : null,
              };
            })()""",
            timeout_sec=60.0,
        )
        assert trigger_seen.get("ready") is True, f"Dashboard trigger missing: {trigger_seen}"
        opened = client.evaluate(
            page,
            """(() => {
              const button = document.querySelector('[data-testid="subagent-dashboard-trigger"]');
              if (!button) return false;
              button.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert opened is True, "Dashboard trigger click failed"
        panel_seen = wait_for_state(
            client,
            page,
            """(() => ({
              ready: !!document.querySelector('[data-testid="subagent-dashboard-panel"]'),
            }))()""",
            timeout_sec=30.0,
        )
        assert panel_seen.get("ready") is True, "Dashboard panel did not open"

        # 真实流程：panel 渲染出该 task 的 completed 节点，store 中节点状态为 completed。
        rendered = wait_for_state(
            client,
            page,
            f"""(() => {{
              const store = window.__myrmSubagentStore?.getState?.();
              const node = store?.nodes?.[{json.dumps(task_id)}];
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const text = panel?.textContent || '';
              return {{
                ready: !!node && node.status === 'completed' && /State Completed|已完成|completed/i.test(text),
                status: node?.status ?? null,
                hasNode: !!node,
                text: text.slice(0, 400),
              }};
            }})()""",
            timeout_sec=60.0,
        )
        assert rendered.get("ready") is True, (
            f"Dashboard did not render completed subagent: {rendered}"
        )
