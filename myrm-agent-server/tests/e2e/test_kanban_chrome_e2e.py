"""Real Chrome MCP E2E for Kanban board and task rendering."""

from __future__ import annotations

import json
import os
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    get_first_enabled_model,
    http_json,
    open_mcp_page,
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_board_and_task_render_in_real_ui() -> None:
    marker = str(time.time_ns())
    board_name = f"Chrome MCP Board {marker}"
    task_title = f"Chrome MCP Task {marker}"
    api_url = get_e2e_api_url()
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

    with open_settings_subroute("/settings/kanban") as (client, page):
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


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
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

    with open_settings_subroute(
        f"/settings/kanban?source_chat={chat_id}&board_id={board_id}"
    ) as (client, page):
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


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_task_drawer_shows_attachment_from_board_view() -> None:
    """REST attachment_ids → click attachment badge → drawer shows attachment (real UI)."""
    marker = str(time.time_ns())
    board_name = f"Chrome Attach Board {marker}"
    task_title = f"Chrome Attach Task {marker}"
    file_id = f"chrome-e2e-file-{marker}"
    api_url = get_e2e_api_url()

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

    with open_settings_subroute("/settings/kanban") as (client, page):
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


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
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


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_task_created_via_ui_form_with_model_override() -> None:
    """Real-user flow: open board in UI → inline create form → pick model → submit.

    Verifies model_override selected in the UI form is persisted and shown as a
    badge in the task drawer (same data source as the REST-created path).
    """
    marker = str(time.time_ns())
    board_name = f"Chrome UI-Create Board {marker}"
    task_title = f"Chrome UI-Create Task {marker}"
    api_url = get_e2e_api_url()

    board = http_json(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {"name": board_name, "description": "Chrome UI create form E2E"},
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    with open_settings_subroute("/settings/kanban") as (client, page):
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

            view_ready = wait_for_state(
                client,
                page,
                f"""(() => {{
                  const view = document.querySelector('[data-testid="kanban-board-view"]');
                  const text = view?.textContent || '';
                  return {{ ready: !!view && text.includes({board_name!r}), text }};
                }})()""",
                timeout_sec=90.0,
            )
            assert view_ready.get("ready") is True

            form_opened = client.evaluate(
                page,
                """(() => {
                  const btn = document.querySelector('[data-testid="kanban-add-task-ready"]');
                  if (!btn) return false;
                  btn.click();
                  return true;
                })()""",
                timeout_sec=5.0,
            )
            assert form_opened is True

            form_state = wait_for_state(
                client,
                page,
                """(() => {
                  const sel = document.querySelector('[data-testid="kanban-create-model-select"]');
                  const submit = document.querySelector('[data-testid="kanban-create-submit"]');
                  const titleInput = document.querySelector(
                    'input[placeholder="Task title"], input[placeholder="任务标题"]',
                  );
                  return { ready: !!sel && !!submit && !!titleInput, hasSel: !!sel, hasSubmit: !!submit };
                })()""",
                timeout_sec=60.0,
            )
            assert form_state.get("hasSel") is True
            assert form_state.get("hasSubmit") is True

            chosen_model = client.evaluate(
                page,
                """(() => {
                  const sel = document.querySelector('[data-testid="kanban-create-model-select"]');
                  if (!sel) return null;
                  const options = Array.from(sel.options).map((o) => o.value).filter((v) => v);
                  if (options.length === 0) return null;
                  const value = options[0];
                  const setter = Object.getOwnPropertyDescriptor(
                    HTMLSelectElement.prototype, 'value',
                  ).set;
                  setter.call(sel, value);
                  sel.dispatchEvent(new Event('change', { bubbles: true }));
                  return value;
                })()""",
                timeout_sec=5.0,
            )
            assert isinstance(chosen_model, str) and chosen_model

            title_typed = client.evaluate(
                page,
                f"""(() => {{
                  const input = document.querySelector(
                    'input[placeholder="Task title"], input[placeholder="任务标题"]',
                  );
                  if (!input) return false;
                  const setter = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype, 'value',
                  ).set;
                  setter.call(input, {task_title!r});
                  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                  return true;
                }})()""",
                timeout_sec=5.0,
            )
            assert title_typed is True

            submitted = client.evaluate(
                page,
                """(() => {
                  const submit = document.querySelector('[data-testid="kanban-create-submit"]');
                  if (!submit) return false;
                  submit.click();
                  return true;
                })()""",
                timeout_sec=5.0,
            )
            assert submitted is True

            created_state = wait_for_state(
                client,
                page,
                f"""(() => {{
                  const view = document.querySelector('[data-testid="kanban-board-view"]');
                  const text = view?.textContent || '';
                  return {{ ready: !!view && text.includes({task_title!r}), text }};
                }})()""",
                timeout_sec=120.0,
            )
            assert created_state.get("ready") is True

            task_id = http_json(
                "GET",
                f"{api_url}/api/v1/kanban/boards/{board_id}/tasks?status=ready",
            )
            assert isinstance(task_id, dict)
            tasks = task_id.get("tasks") or []
            assert isinstance(tasks, list) and len(tasks) == 1
            persisted = tasks[0]
            assert str(persisted.get("model_override") or "") == chosen_model
            assert str(persisted.get("title") or "") == task_title
        finally:
            restore = (
                "localStorage.removeItem('kanban_last_board_id')"
                if previous_board is None
                else "localStorage.setItem('kanban_last_board_id', "
                f"{json.dumps(str(previous_board))})"
            )
            client.evaluate(page, restore, timeout_sec=5.0)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_task_model_override_drawer_badge_edit_and_clear() -> None:
    """model_override persists → drawer badge shows it → edit to inherit clears it (real UI)."""
    marker = str(time.time_ns())
    board_name = f"Chrome Model Board {marker}"
    task_title = f"Chrome Model Task {marker}"
    file_id = f"chrome-e2e-model-file-{marker}"
    api_url = get_e2e_api_url()
    model_override = get_first_enabled_model(api_url)

    board = http_json(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {"name": board_name, "description": "Chrome model override E2E"},
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
            "model_override": model_override,
            "attachment_ids": [file_id],
        },
    )
    assert isinstance(task, dict)
    task_id = str(task.get("task_id") or task.get("id") or "")
    assert task_id
    assert str(task.get("model_override") or "") == model_override

    with open_settings_subroute("/settings/kanban") as (client, page):
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

            card_state = wait_for_state(
                client,
                page,
                f"""(() => {{
                  const card = document.getElementById({json.dumps(f"kanban-task-{task_id}")});
                  return {{ ready: !!card }};
                }})()""",
                timeout_sec=90.0,
            )
            assert card_state.get("ready") is True

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
                  const text = drawer?.textContent || '';
                  return {{ ready: !!drawer && text.includes({model_override!r}), text }};
                }})()""",
                timeout_sec=90.0,
            )
            assert drawer_state.get("ready") is True

            badge_clicked = client.evaluate(
                page,
                f"""(() => {{
                  const drawer =
                    document.querySelector('[data-testid="kanban-task-drawer"]')
                    || document.querySelector('[role="dialog"]');
                  if (!drawer) return false;
                  const badge = Array.from(drawer.querySelectorAll('span')).find(
                    (s) => (s.textContent || '').includes({model_override!r}),
                  );
                  if (!badge) return false;
                  badge.click();
                  return true;
                }})()""",
                timeout_sec=5.0,
            )
            assert badge_clicked is True

            edit_state = wait_for_state(
                client,
                page,
                """(() => {
                  const drawer =
                    document.querySelector('[data-testid="kanban-task-drawer"]')
                    || document.querySelector('[role="dialog"]');
                  if (!drawer) return { ready: false };
                  const sel = Array.from(drawer.querySelectorAll('select')).find(
                    (s) => (s.className || '').includes('chart-2'),
                  );
                  return { ready: !!sel, hasSelect: !!sel };
                })()""",
                timeout_sec=60.0,
            )
            assert edit_state.get("hasSelect") is True

            saved = client.evaluate(
                page,
                """(() => {
                  const drawer =
                    document.querySelector('[data-testid="kanban-task-drawer"]')
                    || document.querySelector('[role="dialog"]');
                  if (!drawer) return false;
                  const sel = Array.from(drawer.querySelectorAll('select')).find(
                    (s) => (s.className || '').includes('chart-2'),
                  );
                  if (!sel) return false;
                  const setter = Object.getOwnPropertyDescriptor(
                    HTMLSelectElement.prototype, 'value',
                  ).set;
                  setter.call(sel, '');
                  sel.dispatchEvent(new Event('change', { bubbles: true }));
                  const box = sel.closest('div');
                  const buttons = Array.from(box?.querySelectorAll('button') || []);
                  if (buttons.length === 0) return false;
                  buttons[0].click();
                  return true;
                })()""",
                timeout_sec=5.0,
            )
            assert saved is True

            wait_for_state(
                client,
                page,
                """(() => {
                  const drawer =
                    document.querySelector('[data-testid="kanban-task-drawer"]')
                    || document.querySelector('[role="dialog"]');
                  if (!drawer) return { ready: true };
                  const sel = Array.from(drawer.querySelectorAll('select')).find(
                    (s) => (s.className || '').includes('chart-2'),
                  );
                  return { ready: !sel };
                })()""",
                timeout_sec=60.0,
            )

            fetched = http_json("GET", f"{api_url}/api/v1/kanban/tasks/{task_id}")
            assert isinstance(fetched, dict)
            assert not fetched.get("model_override")
        finally:
            restore = (
                "localStorage.removeItem('kanban_last_board_id')"
                if previous_board is None
                else "localStorage.setItem('kanban_last_board_id', "
                f"{json.dumps(str(previous_board))})"
            )
            client.evaluate(page, restore, timeout_sec=5.0)
