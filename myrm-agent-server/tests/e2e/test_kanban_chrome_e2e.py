"""Real Chrome MCP E2E for Kanban board and task rendering."""

from __future__ import annotations

import json
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_board_and_task_render_in_real_ui() -> None:
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

    task = http_json(
        "POST",
        f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
        {"title": task_title, "priority": "low", "initial_status": "ready"},
    )
    assert isinstance(task, dict)
    task_id = str(task.get("task_id") or task.get("id") or "")
    assert task_id

    with open_mcp_page(f"{ui_url}/settings/kanban") as (client, page):
        previous_board = client.evaluate(
            page,
            "localStorage.getItem('kanban_last_board_id')",
            timeout_sec=5.0,
        )
        try:
            client.evaluate(
                page,
                "localStorage.removeItem('kanban_last_board_id')",
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
        finally:
            restore = (
                "localStorage.removeItem('kanban_last_board_id')"
                if previous_board is None
                else "localStorage.setItem('kanban_last_board_id', "
                f"{json.dumps(str(previous_board))})"
            )
            client.evaluate(page, restore, timeout_sec=5.0)


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_source_chat_deep_link_filters_board_view() -> None:
    """URL ?source_chat=&board_id= shows only tasks from that chat session."""
    marker = str(time.time_ns())
    board_name = f"Chrome SourceChat Board {marker}"
    chat_id = f"chrome-chat-{marker}"
    in_chat_title = f"In Chat Task {marker}"
    other_title = f"Other Chat Task {marker}"
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    board = http_json(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {"name": board_name, "description": "source_chat deep link E2E"},
    )
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    http_json(
        "POST",
        f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
        {
            "title": in_chat_title,
            "priority": "low",
            "initial_status": "ready",
            "metadata": {"source_chat_id": chat_id},
        },
    )
    http_json(
        "POST",
        f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
        {
            "title": other_title,
            "priority": "low",
            "initial_status": "ready",
            "metadata": {"source_chat_id": "other-chat-id"},
        },
    )

    deep_link = f"{ui_url}/settings/kanban?source_chat={chat_id}&board_id={board_id}"
    with open_mcp_page(deep_link) as (client, page):
        view_state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const view = document.querySelector('[data-testid="kanban-board-view"]');
              const text = view?.textContent || '';
              return {{
                ready: !!view && text.includes({in_chat_title!r}) && !text.includes({other_title!r}),
                text,
              }};
            }})()""",
            timeout_sec=90.0,
        )
        assert in_chat_title in str(view_state.get("text") or "")
        assert other_title not in str(view_state.get("text") or "")


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_task_drawer_shows_attachment_from_board_view() -> None:
    """REST attachment_ids → click attachment badge → drawer shows attachment (real UI)."""
    marker = str(time.time_ns())
    board_name = f"Chrome Attach Board {marker}"
    task_title = f"Chrome Attach Task {marker}"
    file_id = f"chrome-e2e-file-{marker}"
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    board = http_json(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {"name": board_name, "description": "Chrome drawer attachment E2E"},
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    task = http_json(
        "POST",
        f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
        {
            "title": task_title,
            "priority": "low",
            "initial_status": "ready",
            "attachment_ids": [file_id],
        },
    )
    assert isinstance(task, dict)
    task_id = str(task.get("task_id") or task.get("id") or "")
    assert task_id

    with open_mcp_page(f"{ui_url}/settings/kanban") as (client, page):
        previous_board = client.evaluate(
            page,
            "localStorage.getItem('kanban_last_board_id')",
            timeout_sec=5.0,
        )
        try:
            client.evaluate(
                page,
                "localStorage.removeItem('kanban_last_board_id')",
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
            clicked_board = client.evaluate(
                page,
                f"""(() => {{
                  const row = document.querySelector('[data-testid="kanban-board-row-{board_id}"]');
                  if (!row) return false;
                  row.click();
                  return true;
                }})()""",
                timeout_sec=5.0,
            )
            assert clicked_board is True

            task_state = wait_for_state(
                client,
                page,
                f"""(() => {{
                  const card = document.getElementById({json.dumps(f"kanban-task-{task_id}")});
                  const view = document.querySelector('[data-testid="kanban-board-view"]');
                  const text = view?.textContent || '';
                  return {{
                    ready: !!card && !!view && text.includes({task_title!r}),
                    card: !!card,
                  }};
                }})()""",
                timeout_sec=90.0,
            )
            assert task_state.get("card") is True

            drawer_opened = client.evaluate(
                page,
                f"""(() => {{
                  const badge = document.querySelector(
                    '[data-testid="kanban-task-attachment-badge-{task_id}"]',
                  );
                  if (!badge) return false;
                  badge.click();
                  return true;
                }})()""",
                timeout_sec=5.0,
            )
            assert drawer_opened is True

            drawer_state = wait_for_state(
                client,
                page,
                f"""(() => {{
                  const drawer =
                    document.querySelector('[data-testid="kanban-task-drawer"]')
                    || document.querySelector('[role="dialog"]');
                  const attachment =
                    document.querySelector('[data-testid="kanban-attachment-{file_id}"]')
                    || Array.from(drawer?.querySelectorAll('a') || []).find(
                      (link) => (link.textContent || '').includes({file_id!r}),
                    );
                  const text = drawer?.textContent || '';
                  return {{
                    ready: !!drawer && !!attachment && text.includes({file_id!r}),
                    drawer: !!drawer,
                    attachment: !!attachment,
                  }};
                }})()""",
                timeout_sec=90.0,
            )
            assert drawer_state.get("drawer") is True
            assert drawer_state.get("attachment") is True
        finally:
            restore = (
                "localStorage.removeItem('kanban_last_board_id')"
                if previous_board is None
                else "localStorage.setItem('kanban_last_board_id', "
                f"{json.dumps(str(previous_board))})"
            )
            client.evaluate(page, restore, timeout_sec=5.0)


def _seed_kanban_closure_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json(
        "POST", f"{api_url}/api/v1/chats/test/seed-kanban-closure-fixture"
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    board_id = str(seeded.get("board_id") or "")
    task_id = str(seeded.get("task_id") or "")
    task_title = str(seeded.get("task_title") or "")
    assert chat_id.startswith("e2ekanban")
    assert len(board_id) >= 8
    assert len(task_id) >= 8
    assert task_title
    return seeded


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_chat_created_card_opens_filtered_board_view() -> None:
    """Seed chat with KanbanTaskCreatedCard → click open board → filtered board shows task."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_kanban_closure_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    board_id = str(seeded["board_id"])
    task_id = str(seeded["task_id"])
    task_title = str(seeded["task_title"])
    deep_link_path = str(seeded.get("board_deep_link_path") or "")

    warm_ui_route(f"/{chat_id}")
    if deep_link_path.startswith("/"):
        warm_ui_route(deep_link_path)

    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        card_state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const card = document.querySelector(
                '[data-testid="kanban-task-created-card-{task_id}"]',
              );
              const text = card?.textContent || '';
              return {{
                ready: !!card && text.includes({task_title!r}),
                card: !!card,
              }};
            }})()""",
            timeout_sec=90.0,
        )
        assert card_state.get("card") is True

        clicked = client.evaluate(
            page,
            f"""(() => {{
              const button = document.querySelector(
                '[data-testid="kanban-task-created-open-board-{task_id}"]',
              );
              if (!button) return false;
              button.click();
              return true;
            }})()""",
            timeout_sec=5.0,
        )
        assert clicked is True

        nav_state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const params = new URLSearchParams(location.search);
              return {{
                ready:
                  location.pathname.endsWith('/settings/kanban')
                  && params.get('source_chat') === {chat_id!r}
                  && params.get('board_id') === {board_id!r},
                pathname: location.pathname,
                search: location.search,
              }};
            }})()""",
            timeout_sec=30.0,
        )
        assert nav_state.get("ready") is True

        client.reload(page, timeout_ms=60_000)
        wait_for_state(
            client,
            page,
            """(() => ({
              ready: !!document.querySelector('[data-testid="app-layout"]'),
            }))()""",
            timeout_sec=90.0,
        )

        board_state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const view = document.querySelector('[data-testid="kanban-board-view"]');
              const text = view?.textContent || '';
              return {{
                ready: !!view && text.includes({task_title!r}),
                view: !!view,
                text,
              }};
            }})()""",
            timeout_sec=120.0,
        )
        assert board_state.get("view") is True
        assert task_title in str(board_state.get("text") or "")
