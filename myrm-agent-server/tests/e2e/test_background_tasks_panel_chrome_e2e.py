"""Real Chrome MCP E2E for Background Tasks panel (shell registry UX)."""

from __future__ import annotations

import time

import pytest

from tests.support.chrome_mcp_e2e import get_e2e_api_url, get_e2e_ui_url, http_json, open_mcp_page, wait_for_state, warm_ui_route

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


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.timeout(180)
def test_background_tasks_panel_opens_and_lists_api() -> None:
    api_base = get_e2e_api_url()
    payload = http_json("GET", f"{api_base}/api/v1/background-tasks")
    assert isinstance(payload, dict)
    assert "tasks" in payload
    registry_ephemeral = payload.get("registry_ephemeral")

    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
        opened = wait_for_state(client, page, _OPEN_PANEL_JS, timeout_sec=30.0)
        assert opened.get("clicked") is True, opened

        panel = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=30.0)
        assert panel.get("ready") is True, panel

        if registry_ephemeral is True:
            notice = client.evaluate(page, _EPHEMERAL_NOTICE_JS, timeout_sec=10.0)
            assert notice.get("hasNotice") is True, notice
        elif registry_ephemeral is False:
            notice = client.evaluate(page, _DURABLE_NOTICE_JS, timeout_sec=10.0)
            assert notice.get("hasNotice") is True, notice


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
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

    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
        opened = wait_for_state(client, page, _OPEN_PANEL_JS, timeout_sec=30.0)
        assert opened.get("clicked") is True, opened

        panel = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=30.0)
        assert panel.get("ready") is True, panel

        failed_row = wait_for_state(client, page, _FAILED_SHELL_ROW_JS, timeout_sec=30.0)
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


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
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

    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
        opened = wait_for_state(client, page, _OPEN_PANEL_JS, timeout_sec=30.0)
        assert opened.get("clicked") is True, opened
        panel = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=30.0)
        assert panel.get("ready") is True, panel

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


_VAULT_LOG_BUTTON_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const btn = Array.from(root.querySelectorAll('button')).find((node) =>
    /View full log|查看完整日志|檢視完整日誌|完全なログ/.test(node.textContent || '')
  );
  if (!btn) {
    return { clicked: false, text: (root.innerText || '').slice(0, 500) };
  }
  btn.click();
  return { clicked: true };
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


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
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

    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
        opened = wait_for_state(client, page, _OPEN_PANEL_JS, timeout_sec=30.0)
        assert opened.get("clicked") is True, opened

        panel = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=30.0)
        assert panel.get("ready") is True, panel

        clicked = client.evaluate(page, _VAULT_LOG_BUTTON_JS, timeout_sec=15.0)
        assert clicked.get("clicked") is True, clicked

        drawer = wait_for_state(client, page, _VAULT_DRAWER_READY_JS, timeout_sec=45.0)
        assert drawer.get("ready") is True, drawer


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.timeout(240)
def test_background_tasks_success_finish_toast_from_seed() -> None:
    api_base = get_e2e_api_url()
    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
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
