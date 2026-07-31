"""Real Chrome MCP E2E for Background Tasks panel media section (R04B)."""

from __future__ import annotations

import json
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
  return { ready: hasTitle, text: text.slice(0, 400) };
})()"""

_MEDIA_RECENT_TOGGLE_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const toggle = root.querySelector('[data-testid="media-recent-toggle"]');
  return { ready: !!toggle };
})()"""

_CLICK_MEDIA_RECENT_TOGGLE_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const toggle = root.querySelector('[data-testid="media-recent-toggle"]');
  if (!toggle) return { clicked: false };
  toggle.click();
  return { clicked: true };
})()"""

_FAILED_TERMINAL_ROW_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const row = root.querySelector('[data-testid="media-task-row-__TASK_ID__"][data-variant="terminal"]');
  const text = row?.innerText || '';
  return {
    ready:
      !!row &&
      /MYRM_E2E_MEDIA_FAILED_PROMPT/.test(text) &&
      /MYRM_E2E_MEDIA_API_ERROR/.test(text) &&
      (/Failed|失败/.test(text)),
    text: text.slice(0, 400),
  };
})()"""

_SUCCEEDED_TERMINAL_ROW_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const row = root.querySelector('[data-testid="media-task-row-__TASK_ID__"][data-variant="terminal"]');
  const text = row?.innerText || '';
  return {
    ready:
      !!row &&
      /MYRM_E2E_MEDIA_SUCCEEDED_PROMPT/.test(text) &&
      (/Completed|已完成/.test(text)),
    text: text.slice(0, 400),
  };
})()"""

_ACTIVE_RUNNING_ROW_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const row = root.querySelector('[data-testid="media-task-row-__TASK_ID__"][data-variant="active"]');
  const cancelBtn = row?.querySelector('[data-testid="media-task-cancel"]');
  const text = row?.innerText || '';
  return {
    ready:
      !!row &&
      !!cancelBtn &&
      /MYRM_E2E_MEDIA_RUNNING_PROMPT/.test(text) &&
      (/Generating|生成中|Running|运行/.test(text)),
    hasCancel: !!cancelBtn,
    text: text.slice(0, 400),
  };
})()"""

_CLICK_MEDIA_NAVIGATE_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const root = popover || document.body;
  const row = root.querySelector('[data-testid="media-task-row-__TASK_ID__"]');
  const navigateBtn = row?.querySelector('[data-testid="media-task-navigate"]');
  if (!navigateBtn) return { clicked: false };
  navigateBtn.click();
  return { clicked: true };
})()"""

_CHAT_ROUTE_READY_JS = """(() => {
  const path = window.location.pathname || '';
  const chatId = __CHAT_ID_JSON__;
  return {
    ready: path.includes(`/chat/${chatId}`) || path.endsWith(`/chat/${chatId}`),
    path,
  };
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


def _expand_recent_section(client: ChromeMcpClient, page: McpPage) -> None:
    toggle_visible = wait_for_state(
        client, page, _MEDIA_RECENT_TOGGLE_JS, timeout_sec=45.0
    )
    assert toggle_visible.get("ready") is True, toggle_visible
    clicked = client.evaluate(page, _CLICK_MEDIA_RECENT_TOGGLE_JS, timeout_sec=10.0)
    assert clicked.get("clicked") is True, clicked


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(180)
def test_media_background_tasks_panel_shows_failed_terminal_in_recent() -> None:
    api_base = get_e2e_api_url()
    seed = http_json(
        "POST",
        f"{api_base}/api/v1/tasks/test/seed-media-fixture?mode=failed",
    )
    assert isinstance(seed, dict)
    task_id = str(seed["task_id"])

    row = http_json("GET", f"{api_base}/api/v1/tasks/{task_id}")
    assert isinstance(row, dict)
    assert row.get("status") == "failed"
    assert row.get("task_type") == "image_generate"

    with _background_tasks_panel(api_base) as (client, page):
        _expand_recent_section(client, page)
        expression = _FAILED_TERMINAL_ROW_JS.replace("__TASK_ID__", task_id)
        failed_row = wait_for_state(client, page, expression, timeout_sec=45.0)
        assert failed_row.get("ready") is True, failed_row


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(180)
def test_media_background_tasks_panel_navigate_to_chat_from_terminal() -> None:
    api_base = get_e2e_api_url()
    seed = http_json(
        "POST",
        f"{api_base}/api/v1/tasks/test/seed-media-fixture?mode=succeeded",
    )
    assert isinstance(seed, dict)
    task_id = str(seed["task_id"])
    chat_id = str(seed["chat_id"])

    with _background_tasks_panel(api_base) as (client, page):
        _expand_recent_section(client, page)
        row_expression = _SUCCEEDED_TERMINAL_ROW_JS.replace("__TASK_ID__", task_id)
        terminal_row = wait_for_state(client, page, row_expression, timeout_sec=45.0)
        assert terminal_row.get("ready") is True, terminal_row

        navigate_expression = _CLICK_MEDIA_NAVIGATE_JS.replace("__TASK_ID__", task_id)
        navigated = client.evaluate(page, navigate_expression, timeout_sec=10.0)
        assert navigated.get("clicked") is True, navigated

        route_expression = _CHAT_ROUTE_READY_JS.replace(
            "__CHAT_ID_JSON__", json.dumps(chat_id)
        )
        route = wait_for_state(client, page, route_expression, timeout_sec=30.0)
        assert route.get("ready") is True, route


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(180)
def test_media_background_tasks_panel_shows_active_running_with_cancel() -> None:
    api_base = get_e2e_api_url()
    seed = http_json(
        "POST",
        f"{api_base}/api/v1/tasks/test/seed-media-fixture?mode=running",
    )
    assert isinstance(seed, dict)
    task_id = str(seed["task_id"])

    row = http_json("GET", f"{api_base}/api/v1/tasks/{task_id}")
    assert isinstance(row, dict)
    assert row.get("status") == "running"

    with _background_tasks_panel(api_base) as (client, page):
        expression = _ACTIVE_RUNNING_ROW_JS.replace("__TASK_ID__", task_id)
        active_row = wait_for_state(client, page, expression, timeout_sec=45.0)
        assert active_row.get("ready") is True, active_row
        assert active_row.get("hasCancel") is True, active_row
