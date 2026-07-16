"""Real Chrome MCP E2E for Kanban board and task rendering."""

from __future__ import annotations

import time

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger


@pytest.mark.chrome_e2e(lane="LIVE_AGENT")
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_kanban_board_and_task_render_in_real_ui(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    marker = str(time.time_ns())
    board_name = f"Chrome MCP Board {marker}"
    task_title = f"Chrome MCP Task {marker}"
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    board = http_json(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {"name": board_name, "description": "formal Chrome MCP E2E"},
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id
    e2e_resource_ledger.register("kanban_board", board_id)

    task = http_json(
        "POST",
        f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
        {"title": task_title, "priority": "low", "initial_status": "ready"},
    )
    assert isinstance(task, dict)
    task_id = str(task.get("task_id") or task.get("id") or "")
    assert task_id
    e2e_resource_ledger.register("kanban_task", task_id)

    with open_mcp_page(f"{ui_url}/settings/kanban") as (client, page):
        client.evaluate(
            page,
            """(() => {
              localStorage.removeItem('kanban_last_board_id');
              return true;
            })()""",
            timeout_sec=5.0,
        )
        client.reload(page, timeout_ms=60_000)
        row_state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const row = document.querySelector('[data-testid="kanban-board-row-{board_id}"]');
              return {{ ready: !!row, text: row?.textContent || '' }};
            }})()""",
            timeout_sec=90.0,
        )
        assert board_name in str(row_state.get("text") or "")
        clicked = client.evaluate(
            page,
            f"""(() => {{
              const row = document.querySelector('[data-testid="kanban-board-row-{board_id}"]');
              if (!row) return false;
              row.click();
              return true;
            }})()""",
            timeout_sec=5.0,
        )
        assert clicked is True
        task_state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const view = document.querySelector('[data-testid="kanban-board-view"]');
              const text = view?.textContent || '';
              return {{ ready: !!view && text.includes({task_title!r}), text }};
            }})()""",
        )
        assert task_title in str(task_state.get("text") or "")
