"""Real Chrome MCP E2E for Background Tasks panel (shell registry UX)."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import get_e2e_api_url, get_e2e_ui_url, http_json, open_mcp_page, wait_for_state, warm_ui_route

_OPEN_PANEL_JS = """(() => {
  const btn = document.querySelector('button[aria-label="Background Tasks"], button[aria-label="后台任务"]');
  if (!btn) {
    return { clicked: false };
  }
  btn.click();
  return { clicked: true };
})()"""

_PANEL_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTitle = /Background Tasks|后台任务/.test(text);
  const hasShellSection = /Shell jobs|Shell 任务/.test(text);
  return { ready: hasTitle && hasShellSection, text: text.slice(0, 400) };
})()"""

_EPHEMERAL_NOTICE_JS = """(() => {
  const text = document.body?.innerText || '';
  return {
    hasNotice:
      /in-memory only|仅保存在内存中|server restarts|服务重启/.test(text),
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


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.timeout(180)
def test_background_tasks_panel_opens_and_lists_api() -> None:
    api_base = get_e2e_api_url()
    payload = http_json("GET", f"{api_base}/api/v1/background-tasks")
    assert isinstance(payload, dict)
    assert "tasks" in payload
    if "registry_ephemeral" in payload:
        assert payload["registry_ephemeral"] is True

    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
        opened = client.evaluate(page, _OPEN_PANEL_JS, timeout_sec=15.0)
        assert opened.get("clicked") is True, opened

        panel = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=30.0)
        assert panel.get("ready") is True, panel

        if isinstance(payload, dict) and payload.get("registry_ephemeral") is True:
            notice = client.evaluate(page, _EPHEMERAL_NOTICE_JS, timeout_sec=10.0)
            assert notice.get("hasNotice") is True, notice


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.timeout(180)
def test_background_tasks_panel_shows_failed_shell_job_from_seed() -> None:
    api_base = get_e2e_api_url()
    seed = http_json(
        "POST",
        f"{api_base}/api/v1/background-tasks/test/seed-shell-fixture?mode=failed",
    )
    assert isinstance(seed, dict)
    pid = int(seed["pid"])
    task_id = str(seed["task_id"])

    row = http_json("GET", f"{api_base}/api/v1/background-tasks/{task_id}")
    assert isinstance(row, dict)
    assert row.get("status") == "failed"
    assert row.get("exit_code") == 42
    assert row.get("error_category") == "nonzero_exit"

    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
        opened = client.evaluate(page, _OPEN_PANEL_JS, timeout_sec=15.0)
        assert opened.get("clicked") is True, opened

        panel = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=30.0)
        assert panel.get("ready") is True, panel

        failed_row = wait_for_state(client, page, _FAILED_SHELL_ROW_JS, timeout_sec=30.0)
        assert failed_row.get("hasExitCode") is True, failed_row
        assert failed_row.get("hasErrorCategory") is True, failed_row
        assert failed_row.get("hasFailedStatus") is True, failed_row
