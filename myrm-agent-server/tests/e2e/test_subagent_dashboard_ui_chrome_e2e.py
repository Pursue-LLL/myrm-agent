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
    wait_for_state,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger

_AGENT_ROOT = Path(__file__).resolve().parents[3]
_PREPARE_LIGHT = _AGENT_ROOT / "scripts/dev/subagent-dashboard-e2e-chat.mjs"

_DELEGATE_QUERY = (
    "请使用 delegate_task_tool 工具创建一个子智能体，必须将 agent_type 参数设置为 'bash_worker'，"
    "wait 设为 false，让它执行 bash 命令 sleep 300。"
    "注意：必须使用原生函数调用（Native Tool Calling / Function Calling）来调用工具，"
    "绝对不要在文本中输出 XML 格式的工具调用！"
)


@pytest.fixture
def light_chat(e2e_resource_ledger: E2EResourceLedger) -> Iterator[dict[str, object]]:
    """Creates a fresh chat without spawning a real subagent (fast UI-injection scope)."""
    if shutil.which("bun") is None:
        pytest.skip("bun is required for subagent dashboard light chat")
    env = os.environ.copy()
    env["WAVE_LEDGER_LEASE_ID"] = e2e_resource_ledger.lease_id
    env["WAVE_LEDGER_NAMESPACE"] = e2e_resource_ledger.namespace
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
    running_subagent: dict[str, object],
) -> None:
    """Stop-all opens the confirm dialog and cancels every running subagent via API."""
    chat_id = str(running_subagent.get("chatId") or "")
    task_id = str(running_subagent.get("taskId") or "")
    assert chat_id and task_id
    tree_row = running_subagent.get("treeRow")
    rows: list[dict[str, object]] = [
        row for row in [tree_row] if isinstance(row, dict)
    ]
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
    ui_url = str(running_subagent.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")

    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_dashboard_seeded(client, page, chat_id, rows)
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
        api_payload = http_json("GET", f"{get_e2e_api_url()}/api/v1/chats/{chat_id}/subagents")
        data = api_payload.get("data") if isinstance(api_payload, dict) else None
        rows_after = [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
        running_after = [row for row in rows_after if row.get("status") == "running"]
        assert (
            not running_after
        ), f"Real subagent still running after stop-all: {running_after}"


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
def test_subagent_dashboard_frontend_full_flow_delegation_and_cancel() -> None:
    """Real user flow: WebUI send → LLM delegation → running subagent → dashboard → cancel."""
    if (
        not os.environ.get("BASIC_API_KEY", "").strip()
        or not os.environ.get("BASIC_MODEL", "").strip()
    ):
        pytest.skip("BASIC_API_KEY and BASIC_MODEL are required")
    ui_base = get_e2e_ui_url()
    with open_mcp_page(ui_base, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        wait_for_state(
            client,
            page,
            """(() => ({
              ready: !!window.__MYRM_E2E_CHAT__?.sendChatMessage && !!window.__MYRM_E2E_SUBAGENT__?.hydrate,
            }))()""",
            timeout_sec=30.0,
        )
        sent = wait_for_state(
            client,
            page,
            f"""(async () => {{
              const bridge = window.__MYRM_E2E_CHAT__;
              if (!bridge?.sendChatMessage) return {{ ready: false, reason: 'bridge missing' }};
              try {{
                const result = await bridge.sendChatMessage({json.dumps(_DELEGATE_QUERY)}, {{
                  waitForStreamCompletion: false,
                }});
                return {{
                  ready: result.ok === true,
                  chatId: result.chatId ?? null,
                  mode: result.mode ?? null,
                  err: result.err ?? null,
                  debug: result.debug ?? null,
                }};
              }} catch (error) {{
                return {{ ready: false, reason: String(error) }};
              }}
            }})()""",
            timeout_sec=150.0,
        )
        assert sent.get("ready") is True, f"Front-end send failed: {sent}"
        chat_id = str(sent.get("chatId") or "")
        assert chat_id, f"sendChatMessage did not return a chatId: {sent}"

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
        assert task_id, f"No running subagent after front-end send: {last_payload!r}"

        ui_url = f"{ui_base}/{chat_id}"
        with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
            _open_subagent_dashboard(client, page, chat_id)
            row = wait_for_state(
                client,
                page,
                f"""(() => {{
                  const cancel = document.querySelector('[data-testid="subagent-cancel-btn"][data-task-id="{task_id}"]')
                    || document.querySelector('[data-testid="subagent-cancel-btn"]');
                  const panelText = document.querySelector('[data-testid="subagent-dashboard-panel"]')?.textContent || '';
                  return {{
                    ready: !!cancel,
                    hasCancel: !!cancel,
                    hasSleep: /sleep/i.test(panelText) || /bash/i.test(panelText),
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
