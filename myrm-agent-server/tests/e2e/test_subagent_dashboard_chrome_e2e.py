"""Real Chrome MCP E2E for viewing and cancelling a running subagent."""

from __future__ import annotations

import json
import selectors
import subprocess
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from dev_gate_contract import MAX_PAGE_TIMEOUT_MS  # noqa: E402

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger

_PREPARE_PREFIX = "E2E_PREPARE_JSON="


def _wait_running_subagent_on_api(
    chat_id: str,
    task_id: str,
    *,
    e2e_resource_ledger: E2EResourceLedger | None = None,
    timeout_sec: float = 120.0,
) -> None:
    if e2e_resource_ledger is not None:
        e2e_resource_ledger.register("chat", chat_id)
    api_url = get_e2e_api_url()
    deadline = time.monotonic() + timeout_sec
    last: object = None
    while time.monotonic() < deadline:
        payload = http_json("GET", f"{api_url}/api/v1/chats/{chat_id}/subagents")
        last = payload
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            for row in data:
                if not isinstance(row, dict):
                    continue
                if (
                    str(row.get("task_id") or "") == task_id
                    and row.get("status") == "running"
                ):
                    return
        time.sleep(2.0)
    raise AssertionError(f"Subagent {task_id} never reached running on API: {last!r}")


def _hydrate_subagent_tree(
    client,
    page,
    chat_id: str,
    *,
    fallback_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    payload = http_json("GET", f"{get_e2e_api_url()}/api/v1/chats/{chat_id}/subagents")
    data = payload.get("data") if isinstance(payload, dict) else None
    rows: list[dict[str, object]] = (
        [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
    )
    if fallback_rows:
        fallback_ids = {str(row.get("task_id") or "") for row in fallback_rows}
        rows = [
            *fallback_rows,
            *[row for row in rows if str(row.get("task_id") or "") not in fallback_ids],
        ]
    raw = client.evaluate(
        page,
        f"""(() => {{
          const rows = {json.dumps(rows)};
          const bridge = window.__MYRM_E2E_SUBAGENT__;
          if (bridge?.hydrate) {{
            bridge.hydrate(rows);
            return {{ ok: true, mode: 'bridge', count: rows.length, nodeCount: bridge.nodeCount?.() ?? null }};
          }}
          window.dispatchEvent(new CustomEvent('subagents_updated', {{
            detail: {{ chat_id: {json.dumps(chat_id)}, tree: rows }}
          }}));
          const store = window.__myrmSubagentStore?.getState?.();
          return {{
            ok: true,
            mode: 'event',
            count: rows.length,
            nodeCount: store ? Object.keys(store.nodes ?? {{}}).length : null,
          }};
        }})()""",
        timeout_sec=10.0,
    )
    return raw if isinstance(raw, dict) else {"value": raw}


def _read_prepare_result(
    process: subprocess.Popen[str], timeout_sec: float
) -> dict[str, object]:
    if process.stdout is None:
        raise RuntimeError("Subagent prepare stdout is unavailable")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout_sec
    diagnostics: list[str] = []
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                remainder = process.stdout.read()
                if remainder:
                    diagnostics.extend(remainder.splitlines())
                raise RuntimeError(
                    f"Subagent prepare exited {process.returncode}: {diagnostics[-20:]}"
                )
            events = selector.select(timeout=min(1.0, deadline - time.monotonic()))
            if not events:
                continue
            line = process.stdout.readline().strip()
            if not line:
                continue
            if line.startswith(_PREPARE_PREFIX):
                payload = json.loads(line.removeprefix(_PREPARE_PREFIX))
                if not isinstance(payload, dict):
                    raise RuntimeError(f"Invalid subagent prepare payload: {payload!r}")
                return payload
            diagnostics.append(line)
    finally:
        selector.close()
    raise TimeoutError(f"Subagent prepare timed out: {diagnostics[-20:]}")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_lists_and_cancels_running_task(
    running_subagent: dict[str, object],
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    chat_id = str(running_subagent.get("chatId") or "")
    task_id = str(running_subagent.get("taskId") or "")
    assert chat_id and task_id
    tree_row = running_subagent.get("treeRow")
    fallback_rows: list[dict[str, object]] = [
        row for row in [tree_row] if isinstance(row, dict)
    ]
    ui_url = str(running_subagent.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    _wait_running_subagent_on_api(
        chat_id,
        task_id,
        e2e_resource_ledger=e2e_resource_ledger,
    )

    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        wait_for_state(
            client,
            page,
            """(() => ({ ready: !!window.__MYRM_E2E_SUBAGENT__?.hydrate && !!window.__MYRM_E2E_CHAT__?.attachToChat }))()""",
            timeout_sec=30.0,
        )
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
        assert (
            attach_result.get("ready") is True
        ), f"attachToChat failed: {attach_result}"
        shell = wait_for_state(
            client,
            page,
            """(() => {
              const state = window.__MYRM_E2E_CHAT__?.getChatShellState?.() ?? {};
              return {
                ready: state.isMessagesLoaded === true && state.notFound !== true && state.loadError !== true,
                state,
              };
            })()""",
            timeout_sec=60.0,
        )
        assert shell.get("ready") is True, f"Chat shell not ready: {shell}"
        trigger_expr = """(() => {
              const button = document.querySelector('[data-testid="subagent-dashboard-trigger"]');
              if (button) return { ready: true };
              const path = location.pathname;
              const onChat = /^\\/[0-9a-f-]{36}$/i.test(path) || path.startsWith('/c-');
              const store = window.__myrmSubagentStore?.getState?.();
              const nodeCount = store ? Object.keys(store.nodes ?? {}).length : 0;
              return {
                ready: false,
                onChat,
                path,
                nodeCount,
                bridge: !!window.__MYRM_E2E_SUBAGENT__?.hydrate,
                apiBase: typeof window.__MYRM_E2E_API_BASE__ === 'string' ? window.__MYRM_E2E_API_BASE__ : null,
              };
            })()"""
        deadline = time.monotonic() + 90.0
        trigger: dict[str, object] = {"ready": False}
        last_hydrate: dict[str, object] = {}
        while time.monotonic() < deadline:
            last_hydrate = _hydrate_subagent_tree(
                client,
                page,
                chat_id,
                fallback_rows=fallback_rows,
            )
            raw = client.evaluate(page, trigger_expr, timeout_sec=10.0)
            trigger = raw if isinstance(raw, dict) else {"value": raw}
            if trigger.get("ready") is True:
                break
            time.sleep(1.0)
        assert (
            trigger.get("ready") is True
        ), f"Subagent dashboard trigger missing: {trigger}; lastHydrate={last_hydrate}"
        clicked = client.evaluate(
            page,
            """(() => {
              const button = document.querySelector('[data-testid="subagent-dashboard-trigger"]');
              if (!button) return false;
              button.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert clicked is True
        wait_for_state(
            client,
            page,
            """(() => ({
              ready: !!document.querySelector('[data-testid="subagent-dashboard-panel"]'),
            }))()""",
            timeout_sec=30.0,
        )
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
                hasSleepTask: /sleep\\s+300/i.test(panelText),
              }};
            }})()""",
            timeout_sec=90.0,
        )
        assert row.get("hasCancel") is True, f"Cancel button missing: {row}"
        cancelled = client.evaluate(
            page,
            f"""( () => {{
              const button = document.querySelector('[data-testid="subagent-cancel-btn"][data-task-id="{task_id}"]')
                || document.querySelector('[data-testid="subagent-cancel-btn"]');
              if (!button) return false;
              button.click();
              return true;
            }})()""",
            timeout_sec=5.0,
        )
        assert cancelled is True
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


def _open_subagent_dashboard(
    client,
    page,
    chat_id: str,
    *,
    fallback_rows: list[dict[str, object]] | None = None,
) -> None:
    wait_for_state(
        client,
        page,
        """(() => ({ ready: !!window.__MYRM_E2E_SUBAGENT__?.hydrate && !!window.__MYRM_E2E_CHAT__?.attachToChat }))()""",
        timeout_sec=30.0,
    )
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
    shell = wait_for_state(
        client,
        page,
        """(() => {
          const state = window.__MYRM_E2E_CHAT__?.getChatShellState?.() ?? {};
          return {
            ready: state.isMessagesLoaded === true && state.notFound !== true && state.loadError !== true,
            state,
          };
        })()""",
        timeout_sec=60.0,
    )
    assert shell.get("ready") is True, f"Chat shell not ready: {shell}"
    trigger_expr = """(() => {
          const button = document.querySelector('[data-testid="subagent-dashboard-trigger"]');
          if (button) return { ready: true };
          const store = window.__myrmSubagentStore?.getState?.();
          const nodes = store?.nodes ?? {};
          return {
            ready: false,
            nodeCount: Object.keys(nodes).length,
            statuses: Object.values(nodes).map((n) => n?.status),
            hasBridge: !!window.__MYRM_E2E_SUBAGENT__?.hydrate,
            apiBase: typeof window.__MYRM_E2E_API_BASE__ === 'string' ? window.__MYRM_E2E_API_BASE__ : null,
          };
        })()"""
    deadline = time.monotonic() + 90.0
    trigger: dict[str, object] = {"ready": False}
    last_hydrate: dict[str, object] = {}
    while time.monotonic() < deadline:
        last_hydrate = _hydrate_subagent_tree(
            client,
            page,
            chat_id,
            fallback_rows=fallback_rows,
        )
        raw = client.evaluate(page, trigger_expr, timeout_sec=10.0)
        trigger = raw if isinstance(raw, dict) else {"value": raw}
        if trigger.get("ready") is True:
            break
        time.sleep(1.0)
    assert (
        trigger.get("ready") is True
    ), f"Subagent dashboard trigger missing: {trigger}; lastHydrate={last_hydrate}"
    clicked = client.evaluate(
        page,
        """(() => {
          const button = document.querySelector('[data-testid="subagent-dashboard-trigger"]');
          if (!button) return false;
          button.click();
          return true;
        })()""",
        timeout_sec=5.0,
    )
    assert clicked is True
    wait_for_state(
        client,
        page,
        """(() => ({
          ready: !!document.querySelector('[data-testid="subagent-dashboard-panel"]'),
        }))()""",
        timeout_sec=30.0,
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_delegation_pause_toggle_roundtrip(
    running_subagent: dict[str, object],
) -> None:
    chat_id = str(running_subagent.get("chatId") or "")
    task_id = str(running_subagent.get("taskId") or "")
    assert chat_id and task_id
    tree_row = running_subagent.get("treeRow")
    fallback_rows: list[dict[str, object]] = [
        row for row in [tree_row] if isinstance(row, dict)
    ]
    ui_url = str(running_subagent.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    _wait_running_subagent_on_api(chat_id, task_id)

    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_subagent_dashboard(
            client,
            page,
            chat_id,
            fallback_rows=fallback_rows,
        )
        pause_cycle = wait_for_state(
            client,
            page,
            f"""(async () => {{
              const chatId = {json.dumps(chat_id)};
              const apiBase = window.__MYRM_E2E_API_BASE__ || '';
              const statusUrl = `${{apiBase}}/api/v1/chats/${{chatId}}/subagents/delegation/status`;
              const toggle = document.querySelector('[data-testid="delegation-pause-toggle"]');
              if (!toggle) return {{ ready: false, reason: 'toggle missing' }};
              const before = await fetch(statusUrl, {{ credentials: 'include' }}).then((r) => r.json());
              toggle.click();
              await new Promise((resolve) => setTimeout(resolve, 1200));
              const paused = await fetch(statusUrl, {{ credentials: 'include' }}).then((r) => r.json());
              toggle.click();
              await new Promise((resolve) => setTimeout(resolve, 1200));
              const resumed = await fetch(statusUrl, {{ credentials: 'include' }}).then((r) => r.json());
              return {{
                ready: before?.data?.paused === false
                  && paused?.data?.paused === true
                  && resumed?.data?.paused === false,
                before: before?.data?.paused,
                paused: paused?.data?.paused,
                resumed: resumed?.data?.paused,
              }};
            }})()""",
            timeout_sec=60.0,
        )
        assert (
            pause_cycle.get("ready") is True
        ), f"Delegation pause toggle failed: {pause_cycle}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_shows_running_token_and_model(
    running_subagent: dict[str, object],
) -> None:
    chat_id = str(running_subagent.get("chatId") or "")
    task_id = str(running_subagent.get("taskId") or "")
    assert chat_id and task_id
    tree_row = running_subagent.get("treeRow")
    enriched_row: dict[str, object] = (
        {
            **tree_row,
            "token_usage": {"total_tokens": 1234},
            "effective_model": "mimo-v2.5-pro",
        }
        if isinstance(tree_row, dict)
        else {
            "task_id": task_id,
            "status": "running",
            "agent_type": "bash_worker",
            "token_usage": {"total_tokens": 1234},
            "effective_model": "mimo-v2.5-pro",
        }
    )
    ui_url = str(running_subagent.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")

    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_subagent_dashboard(
            client,
            page,
            chat_id,
            fallback_rows=[enriched_row],
        )
        display = wait_for_state(
            client,
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const text = panel?.textContent || '';
              return {
                ready: /1,?234\\s*tok/i.test(text) && /mimo-v2\\.5-pro/i.test(text),
                text: text.slice(0, 500),
              };
            })()""",
            timeout_sec=30.0,
        )
        assert display.get("ready") is True, f"Token/model not rendered: {display}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_shows_token_and_cost_budget_used_limit(
    running_subagent: dict[str, object],
) -> None:
    chat_id = str(running_subagent.get("chatId") or "")
    task_id = str(running_subagent.get("taskId") or "")
    assert chat_id and task_id
    tree_row = running_subagent.get("treeRow")
    budget_row: dict[str, object] = (
        {
            **tree_row,
            "token_usage": {"total_tokens": 12345, "total_cost_usd": 0.5},
            "budget": {"budget_tokens": 100000, "max_cost_usd": 2.5},
            "effective_model": "mimo-v2.5-pro",
        }
        if isinstance(tree_row, dict)
        else {
            "task_id": task_id,
            "status": "running",
            "agent_type": "bash_worker",
            "token_usage": {"total_tokens": 12345, "total_cost_usd": 0.5},
            "budget": {"budget_tokens": 100000, "max_cost_usd": 2.5},
            "effective_model": "mimo-v2.5-pro",
        }
    )
    ui_url = str(running_subagent.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")

    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_subagent_dashboard(
            client,
            page,
            chat_id,
            fallback_rows=[budget_row],
        )
        display = wait_for_state(
            client,
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const text = panel?.textContent || '';
              const tokenTitle = panel?.querySelector('[title*="100,000"]')?.getAttribute('title') || '';
              const costTitle = panel?.querySelector('[title*="$"]')?.getAttribute('title') || '';
              return {
                ready: /12k\\s*\\/\\s*100k\\s*tok/i.test(text)
                  && /\\$0\\.500\\s*\\/\\s*2\\.50/i.test(text),
                text: text.slice(0, 500),
                tokenTitle,
                costTitle,
              };
            })()""",
            timeout_sec=30.0,
        )
        assert (
            display.get("ready") is True
        ), f"Budget used/limit not rendered: {display}"
        token_title = str(display.get("tokenTitle") or "")
        assert (
            "12,345" in token_title and "/" in token_title and "100,000" in token_title
        ), f"Token budget tooltip missing: {display}"
        cost_title = str(display.get("costTitle") or "")
        assert (
            "$0.500" in cost_title and "/" in cost_title and "$2.50" in cost_title
        ), f"Cost budget tooltip missing: {display}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_canvas_topology_renders_and_locates(
    running_subagent: dict[str, object],
) -> None:
    """Canvas topology view renders the live subagent graph and click-to-locate works."""
    chat_id = str(running_subagent.get("chatId") or "")
    task_id = str(running_subagent.get("taskId") or "")
    assert chat_id and task_id
    tree_row = running_subagent.get("treeRow")
    fallback_rows: list[dict[str, object]] = [
        row for row in [tree_row] if isinstance(row, dict)
    ]
    ui_url = str(running_subagent.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")

    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_subagent_dashboard(
            client,
            page,
            chat_id,
            fallback_rows=fallback_rows,
        )
        switched = client.evaluate(
            page,
            """(() => {
              const tab = document.querySelector('[data-testid="subagent-view-tab-canvas"]');
              if (!tab) return false;
              tab.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert switched is True, "Canvas view tab missing"
        canvas = wait_for_state(
            client,
            page,
            """(() => {
              const flow = document.querySelector('.react-flow');
              const nodes = document.querySelectorAll('.react-flow__node');
              return {
                ready: !!flow && nodes.length > 0,
                nodeCount: nodes.length,
                text: document.querySelector('[data-testid="subagent-dashboard-panel"]')?.textContent?.slice(0, 200) || '',
              };
            })()""",
            timeout_sec=30.0,
        )
        assert (
            canvas.get("ready") is True
        ), f"Canvas topology not rendered: {canvas}"
        clicked = client.evaluate(
            page,
            """(() => {
              const node = document.querySelector('.react-flow__node');
              if (!node) return false;
              node.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert clicked is True
        located = wait_for_state(
            client,
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const backOnTree = !!panel?.querySelector('[data-testid="subagent-view-tab-tree"]');
              const locatedNode = document.querySelector('[data-subagent-tree-id]');
              return {
                ready: backOnTree && !!locatedNode,
                hasFlow: !!panel?.querySelector('.react-flow'),
                located: !!locatedNode,
              };
            })()""",
            timeout_sec=30.0,
        )
        assert (
            located.get("ready") is True
        ), f"Click-to-locate did not return to tree view: {located}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_canvas_merges_fission_topology(
    running_subagent: dict[str, object],
) -> None:
    """Canvas topology merges the persisted fission swarm group next to the subagent tree."""
    chat_id = str(running_subagent.get("chatId") or "")
    task_id = str(running_subagent.get("taskId") or "")
    assert chat_id and task_id
    tree_row = running_subagent.get("treeRow")
    fallback_rows: list[dict[str, object]] = [
        row for row in [tree_row] if isinstance(row, dict)
    ]
    ui_url = str(running_subagent.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")

    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_subagent_dashboard(
            client,
            page,
            chat_id,
            fallback_rows=fallback_rows,
        )
        switched = client.evaluate(
            page,
            """(() => {
              const tab = document.querySelector('[data-testid="subagent-view-tab-canvas"]');
              if (!tab) return false;
              tab.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert switched is True, "Canvas view tab missing"
        seeded = client.evaluate(
            page,
            """(() => {
              const store = window.__myrmSubagentStore?.getState?.();
              if (!store?.setFissionTopology) return false;
              store.setFissionTopology({
                fission_id: 'fission-e2e-demo',
                nodes: [
                  { node_id: 'a', agent_type: 'research', objective: 'Research A', status: 'running' },
                  { node_id: 'b', agent_type: 'research', objective: 'Research B', status: 'completed', cost_usd: 0.25 },
                ],
                total_cost_usd: 0.25,
              });
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert seeded is True, "Fission topology seed via store bridge failed"
        merged = wait_for_state(
            client,
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const text = panel?.textContent || '';
              const flow = panel?.querySelector('.react-flow');
              const nodeTexts = Array.from(document.querySelectorAll('.react-flow__node')).map((n) => n.textContent || '');
              return {
                ready: !!flow && nodeTexts.some((t) => /fission-/.test(t))
                  && nodeTexts.some((t) => /Research A/.test(t))
                  && nodeTexts.some((t) => /Research B/.test(t)),
                nodeCount: nodeTexts.length,
                fissionRoot: nodeTexts.filter((t) => /fission-/.test(t)).length,
                summaryText: text.slice(0, 200),
              };
            })()""",
            timeout_sec=30.0,
        )
        assert (
            merged.get("ready") is True
        ), f"Fission topology not merged into canvas: {merged}"
        assert int(merged.get("nodeCount") or 0) >= 3, f"Expected >=3 canvas nodes: {merged}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_tree_renders_gantt_fission_and_filter(
    running_subagent: dict[str, object],
) -> None:
    """Tree view renders the gantt chart, the fission summary banner and live filter controls."""
    chat_id = str(running_subagent.get("chatId") or "")
    task_id = str(running_subagent.get("taskId") or "")
    assert chat_id and task_id
    tree_row = running_subagent.get("treeRow")
    fallback_rows: list[dict[str, object]] = [
        row for row in [tree_row] if isinstance(row, dict)
    ]
    ui_url = str(running_subagent.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")

    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_subagent_dashboard(
            client,
            page,
            chat_id,
            fallback_rows=fallback_rows,
        )
        seeded = client.evaluate(
            page,
            """(() => {
              const store = window.__myrmSubagentStore?.getState?.();
              if (!store) return false;
              const now = Date.now();
              store.setNodes([
                {
                  task_id: 'tree-seed-alpha',
                  parent_task_id: '',
                  agent_type: 'research',
                  description: 'Research Alpha',
                  status: 'running',
                  progress: 40,
                  startedAt: now - 120000,
                  duration_seconds: 300,
                },
                {
                  task_id: 'tree-seed-beta',
                  parent_task_id: '',
                  agent_type: 'review',
                  description: 'Review Beta',
                  status: 'completed',
                  progress: 100,
                  startedAt: now - 90000,
                  duration_seconds: 60,
                },
              ]);
              store.setFissionBatch({
                active: true,
                total: 3,
                completed: 1,
                failed: 1,
                partial: true,
              });
              return true;
            })()""",
            timeout_sec=10.0,
        )
        assert seeded is True, "Tree seed via store bridge failed"
        tree_view = wait_for_state(
            client,
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const summary = panel?.querySelector('[data-testid="subagent-fission-summary"]');
              const gantt = panel?.querySelector('[data-testid="subagent-gantt"]');
              return {
                ready: !!summary && !!gantt,
                hasSummary: !!summary,
                hasGantt: !!gantt,
                summaryText: summary?.textContent || '',
                panelText: panel?.textContent?.slice(0, 400) || '',
              };
            })()""",
            timeout_sec=30.0,
        )
        assert (
            tree_view.get("ready") is True
        ), f"Fission summary or gantt missing: {tree_view}"
        summary_text = str(tree_view.get("summaryText") or "")
        assert (
            "/3" in summary_text and "1" in summary_text
        ), f"Fission partial progress (1/3) not rendered: {tree_view}"
        summary_cls = client.evaluate(
            page,
            """(() => {
              const el = document.querySelector('[data-testid="subagent-fission-summary"]');
              return el ? (el.className || '') : '';
            })()""",
            timeout_sec=5.0,
        )
        assert (
            isinstance(summary_cls, str) and "border-amber" in summary_cls
        ), f"Fission failed summary should use warning style: {summary_cls}"
        gantt_expanded = client.evaluate(
            page,
            """(() => {
              const toggle = document.querySelector('[data-testid="subagent-gantt-toggle"]');
              if (!toggle) return false;
              toggle.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert gantt_expanded is True, "Gantt toggle missing"
        gantt_bars = wait_for_state(
            client,
            page,
            """(() => {
              const gantt = document.querySelector('[data-testid="subagent-gantt"]');
              const labels = gantt ? Array.from(gantt.querySelectorAll('span[title]')).map((n) => n.getAttribute('title') || '') : [];
              return {
                ready: labels.length >= 2 && labels.some((l) => /Research Alpha/.test(l)) && labels.some((l) => /Review Beta/.test(l)),
                labels,
              };
            })()""",
            timeout_sec=15.0,
        )
        assert gantt_bars.get("ready") is True, f"Gantt bars missing: {gantt_bars}"
        filter_result = wait_for_state(
            client,
            page,
            """(() => {
              const runningBtn = document.querySelector('[data-testid="subagent-filter-running"]');
              if (!runningBtn) return { ready: false, reason: 'filter-running missing' };
              runningBtn.click();
              return { ready: true };
            })()""",
            timeout_sec=10.0,
        )
        assert filter_result.get("ready") is True, filter_result
        filtered = wait_for_state(
            client,
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const text = panel?.textContent || '';
              return {
                ready: /Research Alpha/.test(text) && !/Review Beta/.test(text),
                text: text.slice(0, 400),
              };
            })()""",
            timeout_sec=15.0,
        )
        assert filtered.get("ready") is True, f"Filter running did not hide completed: {filtered}"
        all_restored = client.evaluate(
            page,
            """(() => {
              const allBtn = document.querySelector('[data-testid="subagent-filter-all"]');
              if (!allBtn) return false;
              allBtn.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert all_restored is True
        restored = wait_for_state(
            client,
            page,
            """(() => {
              const panel = document.querySelector('[data-testid="subagent-dashboard-panel"]');
              const text = panel?.textContent || '';
              return {
                ready: /Research Alpha/.test(text) && /Review Beta/.test(text),
                text: text.slice(0, 400),
              };
            })()""",
            timeout_sec=15.0,
        )
        assert restored.get("ready") is True, f"Filter all did not restore nodes: {restored}"
