"""Real Chrome MCP E2E for viewing and cancelling a running subagent."""

from __future__ import annotations

import json
import os
import selectors
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

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger

_AGENT_ROOT = Path(__file__).resolve().parents[3]
_PREPARE = _AGENT_ROOT / "scripts/dev/subagent-dashboard-e2e-prepare.mjs"
_PREPARE_PREFIX = "E2E_PREPARE_JSON="


def _wait_running_subagent_on_api(
    chat_id: str,
    task_id: str,
    *,
    timeout_sec: float = 120.0,
) -> None:
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
                if str(row.get("task_id") or "") == task_id and row.get("status") == "running":
                    return
        time.sleep(2.0)
    raise AssertionError(f"Subagent {task_id} never reached running on API: {last!r}")


def _hydrate_subagent_tree(
    client,
    page,
    chat_id: str,
    *,
    task_id: str,
    fallback_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    payload = http_json("GET", f"{get_e2e_api_url()}/api/v1/chats/{chat_id}/subagents")
    data = payload.get("data") if isinstance(payload, dict) else None
    rows: list[dict[str, object]] = [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
    if not any(str(row.get("task_id") or "") == task_id for row in rows) and fallback_rows:
        rows = [*fallback_rows, *rows]
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


def _read_prepare_result(process: subprocess.Popen[str], timeout_sec: float) -> dict[str, object]:
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
                raise RuntimeError(f"Subagent prepare exited {process.returncode}: {diagnostics[-20:]}")
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


@pytest.fixture
def running_subagent(
    e2e_resource_ledger: E2EResourceLedger,
) -> Iterator[dict[str, object]]:
    if shutil.which("bun") is None:
        pytest.skip("bun is required for subagent dashboard prepare")
    if not os.environ.get("BASIC_API_KEY", "").strip() or not os.environ.get("BASIC_MODEL", "").strip():
        pytest.skip("BASIC_API_KEY and BASIC_MODEL are required")
    env = os.environ.copy()
    env["E2E_HOLD_MS"] = "240000"
    env["WAVE_LEDGER_LEASE_ID"] = e2e_resource_ledger.lease_id
    env["WAVE_LEDGER_NAMESPACE"] = e2e_resource_ledger.namespace
    process = subprocess.Popen(
        ["bun", str(_PREPARE)],
        cwd=str(_AGENT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        yield _read_prepare_result(process, timeout_sec=210.0)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_lists_and_cancels_running_task(
    running_subagent: dict[str, object],
) -> None:
    chat_id = str(running_subagent.get("chatId") or "")
    task_id = str(running_subagent.get("taskId") or "")
    assert chat_id and task_id
    tree_row = running_subagent.get("treeRow")
    fallback_rows: list[dict[str, object]] = (
        [row for row in [tree_row] if isinstance(row, dict)]
    )
    ui_url = str(running_subagent.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    _wait_running_subagent_on_api(chat_id, task_id)

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
                task_id=task_id,
                fallback_rows=fallback_rows,
            )
            raw = client.evaluate(page, trigger_expr, timeout_sec=10.0)
            trigger = raw if isinstance(raw, dict) else {"value": raw}
            if trigger.get("ready") is True:
                break
            time.sleep(1.0)
        assert trigger.get("ready") is True, (
            f"Subagent dashboard trigger missing: {trigger}; lastHydrate={last_hydrate}"
        )
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
    task_id: str,
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
          return { ready: false };
        })()"""
    deadline = time.monotonic() + 90.0
    trigger: dict[str, object] = {"ready": False}
    while time.monotonic() < deadline:
        _hydrate_subagent_tree(
            client,
            page,
            chat_id,
            task_id=task_id,
            fallback_rows=fallback_rows,
        )
        raw = client.evaluate(page, trigger_expr, timeout_sec=10.0)
        trigger = raw if isinstance(raw, dict) else {"value": raw}
        if trigger.get("ready") is True:
            break
        time.sleep(1.0)
    assert trigger.get("ready") is True, f"Subagent dashboard trigger missing: {trigger}"
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


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_subagent_dashboard_delegation_pause_toggle_roundtrip(
    running_subagent: dict[str, object],
) -> None:
    chat_id = str(running_subagent.get("chatId") or "")
    task_id = str(running_subagent.get("taskId") or "")
    assert chat_id and task_id
    tree_row = running_subagent.get("treeRow")
    fallback_rows: list[dict[str, object]] = (
        [row for row in [tree_row] if isinstance(row, dict)]
    )
    ui_url = str(running_subagent.get("uiUrl") or f"{get_e2e_ui_url()}/{chat_id}")
    _wait_running_subagent_on_api(chat_id, task_id)

    with open_mcp_page(ui_url, timeout_ms=MAX_PAGE_TIMEOUT_MS) as (client, page):
        _open_subagent_dashboard(
            client,
            page,
            chat_id,
            task_id=task_id,
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
        assert pause_cycle.get("ready") is True, f"Delegation pause toggle failed: {pause_cycle}"


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
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
        {**tree_row, "token_usage": {"total_tokens": 1234}, "effective_model": "mimo-v2.5-pro"}
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
            task_id=task_id,
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
