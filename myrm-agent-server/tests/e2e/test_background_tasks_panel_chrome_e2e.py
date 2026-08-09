"""Real Chrome MCP E2E for Background Tasks panel (shell registry UX)."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_OPEN_PANEL_JS = """(() => {
  const btn = document.querySelector('button[aria-label="Background Tasks"], button[aria-label="后台任务"]');
  if (!btn) {
    return { ready: false, clicked: false };
  }
  btn.click();
  return { ready: true, clicked: true };
})()"""

_PANEL_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTitle = /Background Tasks|后台任务/.test(text);
  const hasShellSection = /Long-running tasks|耗时任务/.test(text);
  return { ready: hasTitle && hasShellSection, text: text.slice(0, 400) };
})()"""

_EPHEMERAL_NOTICE_JS = """(() => {
  const text = document.body?.innerText || '';
  return {
    hasNotice:
      /in-memory only|仅保存在内存中|server restarts|服务重启/.test(text),
  };
})()"""

_DURABLE_NOTICE_JS = """(() => {
  const text = document.body?.innerText || '';
  return {
    hasNotice:
      /Long-running task history is saved|耗时任务历史已保存|Interrupted|已中断/.test(text),
  };
})()"""

_FAILED_SHELL_ROW_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasExitCode = /exit\\s*42|退出码.*42/i.test(text);
  const hasErrorCategory = /Non-Zero Exit|非零退出|nonzero_exit/i.test(text);
  const hasFailedStatus = /failed|失败/i.test(text);
  return {
    ready: hasExitCode && hasErrorCategory && hasFailedStatus,
    hasExitCode,
    hasErrorCategory,
    hasFailedStatus,
  };
})()"""

_PANEL_RUNNING_SHELL_CANCEL_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const cancelBtn = root.querySelector('[data-testid="background-task-cancel"]');
  const text = root.innerText || '';
  const hasShell = /Long-running tasks|耗时任务/.test(text);
  return { ready: !!cancelBtn && hasShell, hasCancel: !!cancelBtn };
})()"""


@contextmanager
def _background_tasks_panel(
    api_base: str,
) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    prepare_e2e_ui_session(api_base)
    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        opened = wait_for_state(client, page, _OPEN_PANEL_JS, timeout_sec=60.0)
        assert opened.get("clicked") is True, opened
        panel = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=60.0)
        assert panel.get("ready") is True, panel
        yield client, page


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(180)
def test_background_tasks_panel_opens_and_lists_api() -> None:
    api_base = get_e2e_api_url()
    payload = http_json("GET", f"{api_base}/api/v1/background-tasks")
    assert isinstance(payload, dict)
    assert "tasks" in payload
    registry_ephemeral = payload.get("registry_ephemeral")

    with _background_tasks_panel(api_base) as (client, page):
        if registry_ephemeral is True:
            notice = client.evaluate(page, _EPHEMERAL_NOTICE_JS, timeout_sec=10.0)
            assert notice.get("hasNotice") is True, notice
        elif registry_ephemeral is False:
            notice = client.evaluate(page, _DURABLE_NOTICE_JS, timeout_sec=10.0)
            assert notice.get("hasNotice") is True, notice


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(180)
def test_background_tasks_panel_shows_failed_shell_job_from_seed() -> None:
    api_base = get_e2e_api_url()
    seed = http_json(
        "POST",
        f"{api_base}/api/v1/background-tasks/test/seed-shell-fixture?mode=failed",
    )
    assert isinstance(seed, dict)
    int(seed["pid"])
    task_id = str(seed["task_id"])

    row = http_json("GET", f"{api_base}/api/v1/background-tasks/{task_id}")
    assert isinstance(row, dict)
    assert row.get("status") == "failed"
    assert row.get("exit_code") == 42
    assert row.get("error_category") == "nonzero_exit"

    with _background_tasks_panel(api_base) as (client, page):
        failed_row = wait_for_state(
            client, page, _FAILED_SHELL_ROW_JS, timeout_sec=30.0
        )
        assert failed_row.get("hasExitCode") is True, failed_row
        assert failed_row.get("hasErrorCategory") is True, failed_row
        assert failed_row.get("hasFailedStatus") is True, failed_row


_CANCEL_RUNNING_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const cancelBtn = root.querySelector('[data-testid="background-task-cancel"]');
  if (!cancelBtn) return { clicked: false };
  cancelBtn.click();
  return { clicked: true };
})()"""

_SHELL_INPUT_TOGGLE_VISIBLE_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const toggle = root.querySelector('[data-testid="background-task-shell-input-toggle"]');
  return { ready: !!toggle };
})()"""

_SHELL_INPUT_CLICK_TOGGLE_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const toggle = root.querySelector('[data-testid="background-task-shell-input-toggle"]');
  if (!toggle) return { clicked: false };
  toggle.click();
  return { clicked: true };
})()"""

_SHELL_INPUT_VISIBLE_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const input = root.querySelector('[data-testid="background-task-shell-input"]');
  return { ready: !!input };
})()"""

_SHELL_INPUT_FOCUS_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const input = root.querySelector('[data-testid="background-task-shell-input"]');
  if (!input) return { focused: false };
  input.focus();
  input.click();
  return { focused: true };
})()"""

_SHELL_INPUT_SEND_READY_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const send = root.querySelector('[data-testid="background-task-shell-input-send"]');
  return { ready: !!send && !send.disabled };
})()"""

_SHELL_INPUT_CLICK_SEND_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const send = root.querySelector('[data-testid="background-task-shell-input-send"]');
  if (!send || send.disabled) return { clicked: false, disabled: send?.disabled ?? true };
  send.click();
  return { clicked: true };
})()"""


def _wait_api_task_status(
    api_base: str,
    task_id: str,
    expected_status: str,
    *,
    timeout_sec: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout_sec
    last_status = ""
    while time.monotonic() < deadline:
        row = http_json("GET", f"{api_base}/api/v1/background-tasks/{task_id}")
        assert isinstance(row, dict)
        last_status = str(row.get("status") or "")
        if last_status == expected_status:
            return
        time.sleep(0.5)
    raise AssertionError(
        f"API status expected {expected_status!r} for {task_id}; last={last_status!r}"
    )


def _wait_list_includes_vault_ref(
    api_base: str,
    task_id: str,
    *,
    timeout_sec: float = 45.0,
) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        payload = http_json("GET", f"{api_base}/api/v1/background-tasks")
        assert isinstance(payload, dict)
        tasks = payload.get("tasks")
        assert isinstance(tasks, list)
        for row in tasks:
            if not isinstance(row, dict):
                continue
            if row.get("task_id") == task_id and row.get("vault_log_ref"):
                return
        time.sleep(0.5)
    raise AssertionError(
        f"List API never exposed vault_log_ref for {task_id} within {timeout_sec}s"
    )


def _wait_api_list_waiting_for_input(
    api_base: str,
    task_id: str,
    *,
    timeout_sec: float = 45.0,
) -> None:
    deadline = time.monotonic() + timeout_sec
    last_flags: dict[str, object] = {}
    while time.monotonic() < deadline:
        payload = http_json("GET", f"{api_base}/api/v1/background-tasks")
        assert isinstance(payload, dict)
        tasks = payload.get("tasks")
        assert isinstance(tasks, list)
        for row in tasks:
            if not isinstance(row, dict):
                continue
            if row.get("task_id") != task_id:
                continue
            last_flags = {
                "status": row.get("status"),
                "waiting_for_input": row.get("waiting_for_input"),
            }
            if row.get("waiting_for_input") is True:
                return
        time.sleep(0.5)
    raise AssertionError(
        f"List API never exposed waiting_for_input=true for {task_id} within {timeout_sec}s; "
        f"last={last_flags!r}"
    )


_LIST_HAS_RUNNING_TASK_JS = """(async () => {
  const api = (window.__MYRM_E2E_API_BASE__ || '').replace(/\\/+$/, '');
  if (!api) {
    return { ready: false, phase: 'missing_api_base' };
  }
  try {
    const response = await fetch(`${api}/api/v1/background-tasks`);
    const body = await response.json();
    const rows = Array.isArray(body.tasks) ? body.tasks : [];
    const row = rows.find((item) => item.task_id === __TASK_ID__);
    return {
      ready: !!(row && row.status === 'running'),
      status: row?.status ?? null,
      count: rows.length,
    };
  } catch (error) {
    return { ready: false, error: String(error) };
  }
})()"""


def _panel_shell_row_timeout_sec() -> float:
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        return 90.0
    return 60.0


def _wait_browser_running_task_row(
    client: ChromeMcpClient,
    page: McpPage,
    task_id: str,
    *,
    timeout_sec: float | None = None,
) -> None:
    resolved_timeout = (
        _panel_shell_row_timeout_sec() if timeout_sec is None else timeout_sec
    )
    client.evaluate(page, _REFRESH_PANEL_JS, timeout_sec=10.0)
    expression = _LIST_HAS_RUNNING_TASK_JS.replace("__TASK_ID__", json.dumps(task_id))
    state = wait_for_state(client, page, expression, timeout_sec=resolved_timeout)
    assert state.get("ready") is True, state
    cancel_ready = wait_for_state(
        client, page, _PANEL_RUNNING_SHELL_CANCEL_JS, timeout_sec=resolved_timeout
    )
    assert cancel_ready.get("ready") is True, cancel_ready


_LIST_HAS_WAITING_JS = """(async () => {
  const api = (window.__MYRM_E2E_API_BASE__ || '').replace(/\\/+$/, '');
  if (!api) {
    return { ready: false, phase: 'missing_api_base' };
  }
  try {
    const response = await fetch(`${api}/api/v1/background-tasks`);
    const body = await response.json();
    const rows = Array.isArray(body.tasks) ? body.tasks : [];
    const row = rows.find((item) => item.task_id === __TASK_ID__);
    return {
      ready: !!(row && row.waiting_for_input === true),
      waiting: row?.waiting_for_input ?? null,
      status: row?.status ?? null,
      api,
      count: rows.length,
    };
  } catch (error) {
    return { ready: false, error: String(error) };
  }
})()"""


def _wait_browser_list_waiting_for_input(
    client: ChromeMcpClient,
    page: McpPage,
    task_id: str,
    *,
    timeout_sec: float = 60.0,
) -> None:
    expression = _LIST_HAS_WAITING_JS.replace("__TASK_ID__", json.dumps(task_id))
    state = wait_for_state(client, page, expression, timeout_sec=timeout_sec)
    assert state.get("ready") is True, state


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(300)
def test_background_tasks_panel_cancel_running_shell_via_ui() -> None:
    api_base = get_e2e_api_url()
    seed = http_json(
        "POST",
        f"{api_base}/api/v1/background-tasks/test/seed-shell-fixture?mode=running",
    )
    assert isinstance(seed, dict)
    task_id = str(seed["task_id"])

    _wait_api_task_status(api_base, task_id, "running")

    with _background_tasks_panel(api_base) as (client, page):
        running_cancel = wait_for_state(
            client, page, _PANEL_RUNNING_SHELL_CANCEL_JS, timeout_sec=60.0
        )
        assert running_cancel.get("ready") is True, running_cancel

        cancelled = client.evaluate(page, _CANCEL_RUNNING_JS, timeout_sec=10.0)
        assert cancelled.get("clicked") is True, cancelled

        # Keep the tab alive until cancel POST completes; closing the page aborts fetch.
        deadline = time.monotonic() + 60.0
        final_status = ""
        while time.monotonic() < deadline:
            row = http_json("GET", f"{api_base}/api/v1/background-tasks/{task_id}")
            assert isinstance(row, dict)
            final_status = str(row.get("status", ""))
            if final_status == "cancelled":
                break
            time.sleep(0.5)
        assert final_status == "cancelled"


_VAULT_LIST_HAS_REF_JS = """(async () => {
  const api = (window.__MYRM_E2E_API_BASE__ || '').replace(/\\/+$/, '');
  if (!api) {
    return { ready: false, phase: 'missing_api_base' };
  }
  try {
    const response = await fetch(`${api}/api/v1/background-tasks`);
    const body = await response.json();
    const rows = Array.isArray(body.tasks) ? body.tasks : [];
    const row = rows.find((item) => item.task_id === __TASK_ID__);
    return {
      ready: !!(row && row.vault_log_ref),
      vault: row?.vault_log_ref || null,
      api,
      count: rows.length,
    };
  } catch (error) {
    return { ready: false, error: String(error) };
  }
})()"""


def _wait_browser_list_includes_vault_ref(
    client: ChromeMcpClient,
    page: McpPage,
    task_id: str,
    *,
    timeout_sec: float = 60.0,
) -> None:
    expression = _VAULT_LIST_HAS_REF_JS.replace("__TASK_ID__", json.dumps(task_id))
    state = wait_for_state(client, page, expression, timeout_sec=timeout_sec)
    assert state.get("ready") is True, state


_REFRESH_PANEL_JS = """(() => {
  window.dispatchEvent(new CustomEvent('myrm:background-tasks-changed'));
  return { ok: true };
})()"""

_VAULT_LOG_BUTTON_JS = """(async () => {
  window.dispatchEvent(new CustomEvent('myrm:background-tasks-changed'));
  await new Promise((resolve) => setTimeout(resolve, 400));
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const testBtn = root.querySelector('[data-testid="background-task-view-vault-log"]');
  if (testBtn) {
    testBtn.click();
    return { ready: true, clicked: true, via: 'testid' };
  }
  const btn = Array.from(root.querySelectorAll('button')).find((node) =>
    /View full log|查看完整日志|檢視完整日誌|完全なログ/.test(node.textContent || '')
  );
  if (btn) {
    btn.click();
    return { ready: true, clicked: true, via: 'text' };
  }
  const api = (window.__MYRM_E2E_API_BASE__ || '').replace(/\\/+$/, '');
  let rowVault = null;
  let rowChat = null;
  if (api) {
    try {
      const response = await fetch(`${api}/api/v1/background-tasks`);
      const body = await response.json();
      const rows = Array.isArray(body.tasks) ? body.tasks : [];
      const row = rows.find((item) => item.task_id === __TASK_ID__);
      rowVault = row?.vault_log_ref || null;
      rowChat = row?.chat_id || null;
    } catch (error) {
      return { ready: false, clicked: false, error: String(error) };
    }
  }
  return {
    ready: false,
    clicked: false,
    rowVault,
    rowChat,
    text: (root.innerText || '').slice(0, 500),
  };
})()"""

_VAULT_DRAWER_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  return {
    ready: /MYRM_E2E_VAULT_LINE_84|MYRM_E2E_VAULT_LINE_0/.test(text),
    sample: text.slice(0, 400),
  };
})()"""

_SUCCESS_FINISH_TOAST_JS = """(() => {
  const toastNodes = Array.from(
    document.querySelectorAll('[data-sonner-toast], [data-sonner-toaster] [data-sonner-toast]')
  );
  const toastText = toastNodes.map((node) => node.textContent || '').join(' ');
  const bodyText = document.body?.innerText || '';
  const merged = `${toastText} ${bodyText}`;
  return {
    ready:
      /Background task finished|后台任务已完成|後臺任務已完成|バックグラウンドタスク完了/.test(merged),
    toastText: toastText.slice(0, 400),
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(240)
def test_background_tasks_panel_vault_log_drawer_from_seed() -> None:
    api_base = get_e2e_api_url()
    seed = http_json(
        "POST",
        f"{api_base}/api/v1/background-tasks/test/seed-shell-fixture?mode=completed_with_vault",
    )
    assert isinstance(seed, dict)
    task_id = str(seed["task_id"])
    assert seed.get("vault_log_ref"), seed

    row = http_json("GET", f"{api_base}/api/v1/background-tasks/{task_id}")
    assert isinstance(row, dict)
    assert row.get("vault_log_ref")
    assert row.get("status") == "completed"

    _wait_list_includes_vault_ref(api_base, task_id)

    prepare_e2e_ui_session(api_base)
    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        _wait_browser_list_includes_vault_ref(client, page, task_id)
        opened = wait_for_state(client, page, _OPEN_PANEL_JS, timeout_sec=60.0)
        assert opened.get("clicked") is True, opened
        panel = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=60.0)
        assert panel.get("ready") is True, panel
        vault_expression = _VAULT_LOG_BUTTON_JS.replace(
            "__TASK_ID__", json.dumps(task_id)
        )
        clicked = wait_for_state(client, page, vault_expression, timeout_sec=90.0)
        assert clicked.get("clicked") is True, clicked

        drawer = wait_for_state(client, page, _VAULT_DRAWER_READY_JS, timeout_sec=45.0)
        assert drawer.get("ready") is True, drawer


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(240)
def test_background_tasks_success_finish_toast_from_seed() -> None:
    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)
    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        # Page must be connected to SSE before the job finishes so toast is delivered.
        time.sleep(1.0)
        seed = http_json(
            "POST",
            f"{api_base}/api/v1/background-tasks/test/seed-shell-fixture?mode=success",
        )
        assert isinstance(seed, dict)
        task_id = str(seed["task_id"])

        deadline = time.monotonic() + 45.0
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            state = client.evaluate(page, _SUCCESS_FINISH_TOAST_JS, timeout_sec=10.0)
            if isinstance(state, dict) and state.get("ready"):
                last = state
                break
            if isinstance(state, dict):
                last = state
            time.sleep(0.5)

        assert last.get("ready") is True, last

        row = http_json("GET", f"{api_base}/api/v1/background-tasks/{task_id}")
        assert isinstance(row, dict)
        assert row.get("status") == "completed"


def _wait_api_result_preview_contains(
    api_base: str,
    task_id: str,
    needle: str,
    *,
    timeout_sec: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout_sec
    last_preview = ""
    while time.monotonic() < deadline:
        row = http_json("GET", f"{api_base}/api/v1/background-tasks/{task_id}")
        assert isinstance(row, dict)
        last_preview = str(row.get("result_preview") or "")
        if needle in last_preview:
            return
        time.sleep(0.5)
    raise AssertionError(
        f"result_preview never contained {needle!r} for {task_id}; last={last_preview!r}"
    )


def _wait_api_stdin_closed(
    api_base: str,
    task_id: str,
    *,
    timeout_sec: float = 15.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        row = http_json("GET", f"{api_base}/api/v1/background-tasks/{task_id}")
        assert isinstance(row, dict)
        last = row
        if row.get("waiting_for_input") is False and row.get("stdin_closed") is True:
            return row
        time.sleep(0.5)
    raise AssertionError(
        f"stdin close never reflected for {task_id}; last waiting={last.get('waiting_for_input')!r} "
        f"stdin_closed={last.get('stdin_closed')!r}"
    )


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(240)
def test_background_tasks_panel_shell_stdin_via_ui() -> None:
    api_base = get_e2e_api_url()
    seed = http_json(
        "POST",
        f"{api_base}/api/v1/background-tasks/test/seed-shell-fixture?mode=running_stdin",
    )
    assert isinstance(seed, dict)
    task_id = str(seed["task_id"])

    _wait_api_task_status(api_base, task_id, "running")

    with _background_tasks_panel(api_base) as (client, page):
        progress_timeout = _panel_shell_row_timeout_sec()
        _wait_browser_running_task_row(
            client, page, task_id, timeout_sec=progress_timeout
        )
        toggle_visible = wait_for_state(
            client, page, _SHELL_INPUT_TOGGLE_VISIBLE_JS, timeout_sec=progress_timeout
        )
        assert toggle_visible.get("ready") is True, toggle_visible

        clicked = client.evaluate(page, _SHELL_INPUT_CLICK_TOGGLE_JS, timeout_sec=10.0)
        assert clicked.get("clicked") is True, clicked

        input_visible = wait_for_state(
            client, page, _SHELL_INPUT_VISIBLE_JS, timeout_sec=15.0
        )
        assert input_visible.get("ready") is True, input_visible

        focus = client.evaluate(page, _SHELL_INPUT_FOCUS_JS, timeout_sec=10.0)
        assert focus.get("focused") is True, focus
        client.type_text(page, "hello")

        send_ready = wait_for_state(
            client, page, _SHELL_INPUT_SEND_READY_JS, timeout_sec=15.0
        )
        assert send_ready.get("ready") is True, send_ready

        sent = client.evaluate(page, _SHELL_INPUT_CLICK_SEND_JS, timeout_sec=10.0)
        assert sent.get("clicked") is True, sent

        # Keep the tab alive until stdin POST completes; closing the page aborts fetch.
        _wait_api_result_preview_contains(
            api_base, task_id, "MYRM_STDIN_ECHO:hello", timeout_sec=45.0
        )

        http_json("POST", f"{api_base}/api/v1/background-tasks/{task_id}/cancel")


_WAITING_BADGE_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const badge = root.querySelector('[data-testid="background-task-waiting-for-input"]');
  return { ready: !!badge };
})()"""

_SHELL_INPUT_CLOSE_VISIBLE_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const closeBtn = root.querySelector('[data-testid="background-task-shell-input-close"]');
  return { ready: !!closeBtn };
})()"""

_SHELL_INPUT_CLICK_CLOSE_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const closeBtn = root.querySelector('[data-testid="background-task-shell-input-close"]');
  if (!closeBtn) return { clicked: false };
  closeBtn.click();
  return { clicked: true };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(300)
def test_background_tasks_panel_shell_waiting_badge_and_close_stdin() -> None:
    api_base = get_e2e_api_url()
    seed = http_json(
        "POST",
        f"{api_base}/api/v1/background-tasks/test/seed-shell-fixture?mode=running_stdin_waiting",
    )
    assert isinstance(seed, dict)
    task_id = str(seed["task_id"])

    _wait_api_task_status(api_base, task_id, "running")
    _wait_api_list_waiting_for_input(api_base, task_id, timeout_sec=45.0)

    prepare_e2e_ui_session(api_base)
    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        _wait_browser_list_waiting_for_input(client, page, task_id, timeout_sec=60.0)

        opened = wait_for_state(client, page, _OPEN_PANEL_JS, timeout_sec=60.0)
        assert opened.get("clicked") is True, opened
        panel = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=60.0)
        assert panel.get("ready") is True, panel

        client.evaluate(page, _REFRESH_PANEL_JS, timeout_sec=10.0)

        running_row = wait_for_state(
            client, page, _PANEL_RUNNING_SHELL_CANCEL_JS, timeout_sec=60.0
        )
        assert running_row.get("ready") is True, running_row

        badge = wait_for_state(client, page, _WAITING_BADGE_JS, timeout_sec=60.0)
        assert badge.get("ready") is True, badge

        clicked = client.evaluate(page, _SHELL_INPUT_CLICK_TOGGLE_JS, timeout_sec=10.0)
        assert clicked.get("clicked") is True, clicked

        close_visible = wait_for_state(
            client, page, _SHELL_INPUT_CLOSE_VISIBLE_JS, timeout_sec=30.0
        )
        assert close_visible.get("ready") is True, close_visible

        closed = client.evaluate(page, _SHELL_INPUT_CLICK_CLOSE_JS, timeout_sec=10.0)
        assert closed.get("clicked") is True, closed

        _wait_api_stdin_closed(api_base, task_id, timeout_sec=30.0)

    http_json("POST", f"{api_base}/api/v1/background-tasks/{task_id}/cancel")
