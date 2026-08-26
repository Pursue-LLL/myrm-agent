"""Real Chrome MCP E2E for Kanban board and task rendering."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    ensure_chat_route,
    get_e2e_api_url,
    get_e2e_ui_url,
    get_first_enabled_model,
    http_json,
    navigate_mcp_page,
    open_mcp_page,
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)


def _api_task_get(api_url: str, task_id: str) -> dict[str, object]:
    """GET a task tolerating transient 5xx (shared SQLite can briefly hit
    disk-I/O busy under parallel load; retries are safe for reads)."""
    deadline = time.monotonic() + 30.0
    while True:
        try:
            t = http_json("GET", f"{api_url}/api/v1/kanban/tasks/{task_id}")
            return t if isinstance(t, dict) else {}
        except RuntimeError as exc:
            if "returned 5" not in str(exc) or time.monotonic() >= deadline:
                raise
            time.sleep(1.5)


def _http_json_write(
    method: str,
    url: str,
    body: dict[str, object] | None = None,
    *,
    attempts: int = 10,
) -> dict[str, object]:
    """Run a state-changing request tolerating transient shared-SQLite 5xx.

    A 500 here means the write transaction was rolled back before commit, so
    re-issuing the same payload is safe — no duplicate rows are created. The
    upstream retry window is short under parallel load, so this adds a slower
    test-layer retry loop on top of it.
    """
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            resp = http_json(method, url, body)
            return resp if isinstance(resp, dict) else {}
        except RuntimeError as exc:
            if "returned 5" not in str(exc):
                raise
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2.0)
    assert last_error is not None
    raise last_error


def _is_attach_failure(exc: BaseException) -> bool:
    """True only for shared-UI attach/bridge failures, never body assertion errors."""
    if isinstance(exc, TimeoutError):
        # asyncio.wait_for cancels ensure_react_e2e_bridge on BRIDGE_READY
        # timeout — the dominant chat-attach contention failure mode.
        return True
    message = str(exc).lower()
    return "shared ui session" in message or "react e2e bridge" in message


@contextmanager
def _open_chat_page_with_attach_retry(chat_url: str, *, attempts: int = 3) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    """Open a chat page, retrying on transient shared-UI attach contention.

    The orchestrator's cold-attach path can briefly fail BRIDGE_READY when
    several shared pytest sessions attach to the same UI at once. A short
    backoff between fresh page sessions usually clears the contention. Only
    attach-phase failures (before the test body runs) are retried — assertion
    errors inside the body propagate immediately via the ``entered`` guard.
    """
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        entered = False
        try:
            with open_mcp_page(chat_url) as (client, page):
                entered = True
                yield client, page
            return
        except BaseException as exc:
            last_exc = exc
            if entered or not _is_attach_failure(exc) or attempt + 1 >= attempts:
                raise
            time.sleep(5.0)
    assert last_exc is not None
    raise last_exc


def _api_find_task_by_title(api_url: str, board_id: str, title: str) -> dict[str, object] | None:
    deadline = time.monotonic() + 30.0
    while True:
        try:
            resp = http_json("GET", f"{api_url}/api/v1/kanban/boards/{board_id}/tasks")
            break
        except RuntimeError as exc:
            if "returned 5" not in str(exc) or time.monotonic() >= deadline:
                raise
            time.sleep(1.5)
    items = resp.get("items") if isinstance(resp, dict) else None
    if not isinstance(items, list):
        return None
    for t in items:
        if isinstance(t, dict) and str(t.get("title") or "") == title:
            return t
    return None


def _api_wait_task_status(
    api_url: str,
    task_id: str,
    expected: str,
    *,
    timeout_sec: float = 150.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last = ""
    while time.monotonic() < deadline:
        t = _api_task_get(api_url, task_id)
        st = str(t.get("status") or "")
        if st != last:
            last = st
        if st == expected:
            return t
        if st in ("completed", "failed"):
            break
        time.sleep(2)
    raise AssertionError(f"Task {task_id} did not reach {expected!r}; last status={last!r}")


def _create_task_via_ui(client, page, title: str, description: str) -> str:
    """Fill the READY-column inline form and submit; returns the chosen model id.

    Prefers a minimax route (matches the LITE_MODEL seed) and falls back to the
    first available option so the test never hard-codes a model.
    """
    add_ready = wait_for_state(
        client,
        page,
        """(() => {
          const btn = document.querySelector('[data-testid="kanban-add-task-ready"]');
          return { ready: !!btn };
        })()""",
        timeout_sec=60.0,
    )
    assert add_ready.get("ready") is True
    opened = client.evaluate(
        page,
        """(() => {
          const btn = document.querySelector('[data-testid="kanban-add-task-ready"]');
          if (!btn) return false;
          btn.click();
          return true;
        })()""",
        timeout_sec=5.0,
    )
    assert opened is True
    form_state = wait_for_state(
        client,
        page,
        """(() => {
          const sel = document.querySelector('[data-testid="kanban-create-model-select"]');
          const submit = document.querySelector('[data-testid="kanban-create-submit"]');
          return { ready: !!sel && !!submit, hasSel: !!sel, hasSubmit: !!submit };
        })()""",
        timeout_sec=60.0,
    )
    assert form_state.get("hasSel") is True
    assert form_state.get("hasSubmit") is True

    chosen_model = client.evaluate(
        page,
        """(() => {
          const sel = document.querySelector('[data-testid="kanban-create-model-select"]');
          const options = Array.from(sel.options).map((o) => o.value).filter((v) => v);
          if (options.length === 0) return '';
          const target =
            options.find((v) => v.toLowerCase().includes('minimax')) || options[0];
          const setter = Object.getOwnPropertyDescriptor(
            HTMLSelectElement.prototype, 'value',
          ).set;
          setter.call(sel, target);
          sel.dispatchEvent(new Event('change', { bubbles: true }));
          return target;
        })()""",
        timeout_sec=5.0,
    )
    assert isinstance(chosen_model, str) and chosen_model

    def _set_field(selector: str, value: str) -> bool:
        return bool(
            client.evaluate(
                page,
                f"""(() => {{
                  const el = document.querySelector({json.dumps(selector)});
                  if (!el) return false;
                  const setter = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype, 'value',
                  ).set;
                  setter.call(el, {json.dumps(value)});
                  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                  return true;
                }})()""",
                timeout_sec=5.0,
            )
        )

    assert _set_field(
        'input[placeholder="Task title"], input[placeholder="任务标题"]',
        title,
    )
    assert _set_field(
        'input[placeholder="Task description (optional)"], input[placeholder="任务描述（可选）"]',
        description,
    )
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
    created = wait_for_state(
        client,
        page,
        f"""(() => {{
          const view = document.querySelector('[data-testid="kanban-board-view"]');
          const text = view?.textContent || '';
          return {{ ready: !!view && text.includes({title!r}), text }};
        }})()""",
        timeout_sec=120.0,
    )
    assert created.get("ready") is True
    return chosen_model


def _open_kanban_board(client, page, board_id: str, board_name: str) -> None:
    """Enter the given board's view via its deep-link URL.

    Navigating to /settings/kanban?board_id=... is the frontend's most stable
    entry point (KanbanSection prefers boardIdParam over any persisted last
    board), and unlike reload-then-click it never lands on a blank hydration
    state under shared parallel UI. The deep-link test proves this path.
    """
    ui_base = get_e2e_ui_url().rstrip("/")
    navigate_mcp_page(
        client,
        page,
        f"{ui_base}/settings/kanban?board_id={board_id}",
        timeout_ms=90_000,
    )
    view_state = wait_for_state(
        client,
        page,
        f"""(() => {{
          const view = document.querySelector('[data-testid="kanban-board-view"]');
          const text = view?.textContent || '';
          return {{ ready: !!view && text.includes({board_name!r}), text }};
        }})()""",
        timeout_sec=120.0,
        page_url="/settings/kanban",
        pin_direct_blank_heal=True,
    )
    assert board_name in str(view_state.get("text") or "")


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_board_and_task_render_in_real_ui() -> None:
    marker = str(time.time_ns())
    board_name = f"Chrome MCP Board {marker}"
    task_title = f"Chrome MCP Task {marker}"
    api_url = get_e2e_api_url()
    board = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {"name": board_name, "description": "formal Chrome MCP E2E"},
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    task = _http_json_write(
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
            _open_kanban_board(client, page, board_id, board_name)
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
                else f"localStorage.setItem('kanban_last_board_id', {json.dumps(str(previous_board))})"
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

    board = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {"name": board_name, "description": "source_chat deep link E2E"},
    )
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
        {
            "title": in_chat_title,
            "priority": "low",
            "initial_status": "ready",
            "metadata": {"source_chat_id": chat_id},
        },
    )
    _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
        {
            "title": other_title,
            "priority": "low",
            "initial_status": "ready",
            "metadata": {"source_chat_id": "other-chat-id"},
        },
    )

    with open_settings_subroute(f"/settings/kanban?source_chat={chat_id}&board_id={board_id}") as (client, page):
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

    board = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {"name": board_name, "description": "Chrome drawer attachment E2E"},
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    task = _http_json_write(
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
            _open_kanban_board(client, page, board_id, board_name)

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
                else f"localStorage.setItem('kanban_last_board_id', {json.dumps(str(previous_board))})"
            )
            client.evaluate(page, restore, timeout_sec=5.0)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_stats_bar_shows_running_with_limit() -> None:
    """Stats bar renders `Running: {count}/{limit}` when board max_concurrent_tasks is set.

    Covers Optimization B: the running column switches from `Running: N` to the
    limit-aware `Running: N/M` label sourced from board.settings.max_concurrent_tasks.
    """
    marker = str(time.time_ns())
    board_name = f"Chrome Stats Board {marker}"
    api_url = get_e2e_api_url()

    board = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {
            "name": board_name,
            "description": "Chrome stats bar E2E",
            "max_concurrent_tasks": 1,
        },
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    summary = http_json("GET", f"{api_url}/api/v1/kanban/boards/{board_id}/summary")
    assert isinstance(summary, dict)
    assert summary["board"]["settings"]["max_concurrent_tasks"] == 1

    with open_settings_subroute("/settings/kanban") as (client, page):
        previous_board = client.evaluate(
            page,
            "localStorage.getItem('kanban_last_board_id')",
            timeout_sec=5.0,
        )
        try:
            _open_kanban_board(client, page, board_id, board_name)
            stats_state = wait_for_state(
                client,
                page,
                """(() => {
                  const view = document.querySelector('[data-testid="kanban-board-view"]');
                  const text = view?.textContent || '';
                  return {
                    ready: !!view && text.includes('0/1'),
                    text,
                  };
                })()""",
                timeout_sec=90.0,
            )
            assert "0/1" in str(stats_state.get("text") or "")
        finally:
            restore = (
                "localStorage.removeItem('kanban_last_board_id')"
                if previous_board is None
                else f"localStorage.setItem('kanban_last_board_id', {json.dumps(str(previous_board))})"
            )
            client.evaluate(page, restore, timeout_sec=5.0)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_ready_card_shows_queued_badge_when_concurrency_full() -> None:
    """Ready task shows queued badge when the board concurrency slot is saturated.

    Covers Optimization B: a ready task waiting for a concurrency slot is marked
    on the card. Deterministic fixture: board max_concurrent_tasks=1, T1 is moved
    to running (occupying the only slot) without relying on the dispatcher, T2
    stays ready and must show the badge.
    """
    marker = str(time.time_ns())
    board_name = f"Chrome Queue Board {marker}"
    api_url = get_e2e_api_url()

    board = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {
            "name": board_name,
            "description": "Chrome queued badge E2E",
            "max_concurrent_tasks": 1,
            # Zombie check interval = max(zombie_timeout_seconds // 2, 30) = 900s,
            # far beyond the 180s test window, so the manually RUNNING task is
            # never reclaimed mid-test (shared E2E backend has no LLM runner).
            "zombie_timeout_seconds": 1800,
        },
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    # Create T1 as BLOCKED (the dispatcher never claims blocked tasks), then
    # manually move it to RUNNING to deterministically occupy the only slot —
    # a READY-created task would be claimed by the real dispatcher and fail
    # instantly because the shared E2E backend has no configured LLM.
    running_task = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
        {
            "title": f"Occupying task {marker}",
            "priority": "low",
            "initial_status": "blocked",
        },
    )
    assert isinstance(running_task, dict)
    running_task_id = str(running_task.get("task_id") or running_task.get("id") or "")
    assert running_task_id

    moved = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/tasks/{running_task_id}/move",
        {"status": "running"},
    )
    assert isinstance(moved, dict)
    assert str(moved.get("status") or "") == "running"

    queued_task = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
        {
            "title": f"Queued task {marker}",
            "priority": "low",
            "initial_status": "ready",
        },
    )
    assert isinstance(queued_task, dict)
    queued_task_id = str(queued_task.get("task_id") or queued_task.get("id") or "")
    assert queued_task_id

    summary = http_json("GET", f"{api_url}/api/v1/kanban/boards/{board_id}/summary")
    assert isinstance(summary, dict)
    task_counts = summary.get("task_counts") or {}
    assert task_counts.get("running") == 1
    assert task_counts.get("ready") == 1

    with open_settings_subroute("/settings/kanban") as (client, page):
        _open_kanban_board(client, page, board_id, board_name)
        badge_state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const card = document.getElementById({json.dumps(f"kanban-task-{queued_task_id}")});
              const badge = card?.querySelector('[data-testid="kanban-task-queued-badge"]');
              const badgeText = badge?.textContent?.trim() || '';
              return {{ ready: !!badge, text: badgeText }};
            }})()""",
            timeout_sec=90.0,
        )
        assert badge_state.get("ready") is True
        assert str(badge_state.get("text") or ""), "queued badge rendered but its i18n text is empty"


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_ready_card_shows_no_queued_badge_when_slot_available() -> None:
    """No queued badge is rendered while a concurrency slot is still free.

    Negative counterpart of the queued-badge test: board max_concurrent_tasks=2
    with a single RUNNING task leaves one slot free, so the running card must
    not carry the badge and no queued badge may exist anywhere on the board.
    """
    marker = str(time.time_ns())
    board_name = f"Chrome NoQueue Board {marker}"
    api_url = get_e2e_api_url()

    board = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {
            "name": board_name,
            "description": "Chrome no-queued-badge E2E",
            "max_concurrent_tasks": 2,
            # Same zombie guard as the positive test: keep the manually RUNNING
            # task alive for the whole test window in the shared backend.
            "zombie_timeout_seconds": 1800,
        },
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    running_task = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
        {
            "title": f"Running task {marker}",
            "priority": "low",
            "initial_status": "blocked",
        },
    )
    assert isinstance(running_task, dict)
    running_task_id = str(running_task.get("task_id") or running_task.get("id") or "")
    assert running_task_id

    moved = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/tasks/{running_task_id}/move",
        {"status": "running"},
    )
    assert isinstance(moved, dict)
    assert str(moved.get("status") or "") == "running"

    summary = http_json("GET", f"{api_url}/api/v1/kanban/boards/{board_id}/summary")
    assert isinstance(summary, dict)
    task_counts = summary.get("task_counts") or {}
    assert task_counts.get("running") == 1
    # count_tasks_grouped only emits statuses that exist — no ready tasks means
    # the key is absent, so default to 0 instead of indexing directly.
    assert task_counts.get("ready", 0) == 0

    with open_settings_subroute("/settings/kanban") as (client, page):
        _open_kanban_board(client, page, board_id, board_name)
        board_state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const view = document.querySelector('[data-testid="kanban-board-view"]');
              const card = document.getElementById({json.dumps(f"kanban-task-{running_task_id}")});
              const badges = view?.querySelectorAll('[data-testid="kanban-task-queued-badge"]') || [];
              return {{
                ready: !!view && !!card,
                cardHasBadge: !!card?.querySelector('[data-testid="kanban-task-queued-badge"]'),
                badgeCount: badges.length,
              }};
            }})()""",
            timeout_sec=90.0,
        )
        assert board_state.get("ready") is True
        assert board_state.get("cardHasBadge") is False
        assert board_state.get("badgeCount") == 0


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_kanban_multiple_ready_cards_show_queued_badge() -> None:
    """Every ready card shows the queued badge while the slot is saturated.

    Edge case of Optimization B: with max_concurrent_tasks=1 and one RUNNING
    occupant, TWO ready tasks must both render the badge — the hint is per-card
    and must not be limited to a single queued task. Deterministic fixture
    (blocked→move running) so no LLM execution is involved.
    """
    marker = str(time.time_ns())
    board_name = f"Chrome MultiQueue Board {marker}"
    api_url = get_e2e_api_url()

    board = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {
            "name": board_name,
            "description": "Chrome multi-queued-badge E2E",
            "max_concurrent_tasks": 1,
            "zombie_timeout_seconds": 1800,
        },
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    running_task = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
        {"title": f"Occupying task {marker}", "priority": "low", "initial_status": "blocked"},
    )
    assert isinstance(running_task, dict)
    running_task_id = str(running_task.get("task_id") or running_task.get("id") or "")
    assert running_task_id
    moved = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/tasks/{running_task_id}/move",
        {"status": "running"},
    )
    assert isinstance(moved, dict)
    assert str(moved.get("status") or "") == "running"

    queued_ids: list[str] = []
    for idx in (1, 2):
        task = _http_json_write(
            "POST",
            f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
            {
                "title": f"Queued task {idx} {marker}",
                "priority": "low",
                "initial_status": "ready",
            },
        )
        assert isinstance(task, dict)
        tid = str(task.get("task_id") or task.get("id") or "")
        assert tid
        queued_ids.append(tid)

    summary = http_json("GET", f"{api_url}/api/v1/kanban/boards/{board_id}/summary")
    assert isinstance(summary, dict)
    task_counts = summary.get("task_counts") or {}
    assert task_counts.get("running") == 1
    assert task_counts.get("ready", 0) == 2

    with open_settings_subroute("/settings/kanban") as (client, page):
        _open_kanban_board(client, page, board_id, board_name)
        badge_state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const view = document.querySelector('[data-testid="kanban-board-view"]');
              const q1 = document.getElementById({json.dumps(f"kanban-task-{queued_ids[0]}")});
              const q2 = document.getElementById({json.dumps(f"kanban-task-{queued_ids[1]}")});
              const run = document.getElementById({json.dumps(f"kanban-task-{running_task_id}")});
              const badges = view?.querySelectorAll('[data-testid="kanban-task-queued-badge"]') || [];
              return {{
                ready: !!view && !!q1 && !!q2 && !!run && badges.length === 2,
                q1Badge: !!q1?.querySelector('[data-testid="kanban-task-queued-badge"]'),
                q2Badge: !!q2?.querySelector('[data-testid="kanban-task-queued-badge"]'),
                runningHasBadge: !!run?.querySelector('[data-testid="kanban-task-queued-badge"]'),
                badgeCount: badges.length,
              }};
            }})()""",
            timeout_sec=90.0,
        )
        assert badge_state.get("ready") is True, badge_state
        assert badge_state.get("q1Badge") is True
        assert badge_state.get("q2Badge") is True
        assert badge_state.get("runningHasBadge") is False
        assert badge_state.get("badgeCount") == 2


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(540)
def test_kanban_real_execution_queued_badge_release_flow() -> None:
    """Real-user full flow: create tasks in the UI, dispatcher really executes them
    with the configured LLM, the queued badge appears on the second ready task while
    the only concurrency slot is occupied, and disappears once the slot frees up.

    Unlike the deterministic blocked→running fixtures, this drives the live pipeline
    READY → RUNNING → COMPLETED through real agent execution — the same way a user
    experiences the queued badge under genuine concurrency pressure.
    """
    marker = str(time.time_ns())
    board_name = f"Chrome RealExec Board {marker}"
    t1_title = f"Count letters {marker}"
    t2_title = f"Say done {marker}"
    # Deliberately minimal, imperative prompts (mirror the description that the
    # live pipeline completed deterministically during verification): the worker
    # lifecycle prompt already forces kanban_complete, so a terse instruction
    # leaves the model no room to "finish" without completing the task. Use the
    # same terse shape as the drain test, which passed all three real executions.
    counting_task = "Reply with the word hello. Then call kanban_complete with summary 'hello'. Do not use any tools."
    done_task = "Reply with the word world. Then call kanban_complete with summary 'world'. Do not use any tools."
    api_url = get_e2e_api_url()

    board = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {
            "name": board_name,
            "description": "Chrome real-exec queued badge E2E",
            "max_concurrent_tasks": 1,
            # Zombie guard: heartbeat interval = max(zombie_timeout // 2, 30) = 900s,
            # far beyond the test window, so genuinely RUNNING tasks are never
            # reclaimed mid-execution in the shared backend.
            "zombie_timeout_seconds": 1800,
        },
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    with open_settings_subroute("/settings/kanban") as (client, page):
        _open_kanban_board(client, page, board_id, board_name)

        # T1: created via the UI, then REALLY claimed and executed by the dispatcher.
        _create_task_via_ui(client, page, t1_title, counting_task)
        t1_task = _api_find_task_by_title(api_url, board_id, t1_title)
        assert t1_task is not None
        t1_id = str(t1_task.get("task_id") or "")
        assert t1_id
        _api_wait_task_status(api_url, t1_id, "running")
        running_task = _api_find_task_by_title(api_url, board_id, t1_title)
        assert running_task is not None
        assert str(running_task.get("status") or "") == "running"

        # T2: queued while the only slot is occupied → badge must show on the card.
        _create_task_via_ui(client, page, t2_title, done_task)
        t2_task = _api_find_task_by_title(api_url, board_id, t2_title)
        assert t2_task is not None
        t2_id = str(t2_task.get("task_id") or "")
        assert t2_id

        badge_state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const card = document.getElementById({json.dumps(f"kanban-task-{t2_id}")});
              const badge = card?.querySelector('[data-testid="kanban-task-queued-badge"]');
              const badgeText = badge?.textContent?.trim() || '';
              return {{ ready: !!badge, hasCard: !!card, text: badgeText }};
            }})()""",
            timeout_sec=90.0,
        )
        assert badge_state.get("ready") is True
        assert str(badge_state.get("text") or ""), "queued badge text is empty"

        # T1 really completes → the slot frees.
        t1_done = _api_wait_task_status(api_url, t1_id, "completed", timeout_sec=200.0)
        assert str(t1_done.get("result") or "").strip(), "T1 completed without a summary"

        # T2 is claimed automatically → badge disappears.
        _api_wait_task_status(api_url, t2_id, "running", timeout_sec=200.0)
        badge_gone = wait_for_state(
            client,
            page,
            f"""(() => {{
              const card = document.getElementById({json.dumps(f"kanban-task-{t2_id}")});
              const badge = card?.querySelector('[data-testid="kanban-task-queued-badge"]');
              return {{ ready: !!card && !badge, hasCard: !!card, badge: !!badge }};
            }})()""",
            timeout_sec=90.0,
        )
        assert badge_gone.get("ready") is True

        # Full loop: T2 really completes as well.
        t2_done = _api_wait_task_status(api_url, t2_id, "completed", timeout_sec=200.0)
        assert str(t2_done.get("result") or "").strip(), "T2 completed without a summary"


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_kanban_queued_badge_count_drains_as_slots_release() -> None:
    """Queued badges count drains in FIFO order as real executions release slots.

    Real-user scenario with THREE tasks on a single-slot board: while T1 runs,
    T2 and T3 both carry the badge (count=2); once T1 completes, T2 is claimed
    and only T3 still shows it (count=1); once T2 completes, T3 is claimed and
    the board has no badge left (count=0). Verifies per-card badge state stays
    consistent with the live running-count across the whole drain sequence.
    """
    marker = str(time.time_ns())
    board_name = f"Chrome Drain Board {marker}"
    titles = [f"Say alpha {marker}", f"Say beta {marker}", f"Say gamma {marker}"]
    prompts = [
        "Reply with the word alpha. Then call kanban_complete with summary 'alpha'. Do not use any tools.",
        "Reply with the word beta. Then call kanban_complete with summary 'beta'. Do not use any tools.",
        "Reply with the word gamma. Then call kanban_complete with summary 'gamma'. Do not use any tools.",
    ]
    api_url = get_e2e_api_url()

    board = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {
            "name": board_name,
            "description": "Chrome queued-badge drain E2E",
            "max_concurrent_tasks": 1,
            "zombie_timeout_seconds": 1800,
        },
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    def _task_id_by_title(title: str) -> str:
        task = _api_find_task_by_title(api_url, board_id, title)
        assert task is not None, f"task {title!r} not found"
        tid = str(task.get("task_id") or "")
        assert tid
        return tid

    with open_settings_subroute("/settings/kanban") as (client, page):
        _open_kanban_board(client, page, board_id, board_name)

        # T1 created first → claimed and executed immediately (slot free).
        _create_task_via_ui(client, page, titles[0], prompts[0])
        t1_id = _task_id_by_title(titles[0])
        _api_wait_task_status(api_url, t1_id, "running", timeout_sec=200.0)

        # T2, T3 queue behind the single occupied slot.
        _create_task_via_ui(client, page, titles[1], prompts[1])
        t2_id = _task_id_by_title(titles[1])
        _create_task_via_ui(client, page, titles[2], prompts[2])
        t3_id = _task_id_by_title(titles[2])

        two_badges = wait_for_state(
            client,
            page,
            """(() => {
              const view = document.querySelector('[data-testid="kanban-board-view"]');
              const badges = view?.querySelectorAll('[data-testid="kanban-task-queued-badge"]') || [];
              return { ready: badges.length === 2, count: badges.length };
            })()""",
            timeout_sec=90.0,
        )
        assert two_badges.get("count") == 2, two_badges

        # T1 completes → T2 claimed → only T3 keeps the badge.
        t1_done = _api_wait_task_status(api_url, t1_id, "completed", timeout_sec=240.0)
        assert str(t1_done.get("result") or "").strip()
        _api_wait_task_status(api_url, t2_id, "running", timeout_sec=240.0)
        one_badge = wait_for_state(
            client,
            page,
            f"""(() => {{
              const view = document.querySelector('[data-testid="kanban-board-view"]');
              const badges = view?.querySelectorAll('[data-testid="kanban-task-queued-badge"]') || [];
              const t3 = view && Array.from(view.querySelectorAll('[id^="kanban-task-"]')).find(
                (el) => el.textContent && el.textContent.includes({json.dumps(titles[2])}),
              );
              return {{
                ready: badges.length === 1 && !!t3?.querySelector('[data-testid="kanban-task-queued-badge"]'),
                count: badges.length,
              }};
            }})()""",
            timeout_sec=90.0,
        )
        assert one_badge.get("count") == 1, one_badge

        # T2 completes → T3 claimed → no badge remains anywhere.
        t2_done = _api_wait_task_status(api_url, t2_id, "completed", timeout_sec=240.0)
        assert str(t2_done.get("result") or "").strip()
        _api_wait_task_status(api_url, t3_id, "running", timeout_sec=240.0)
        zero_badges = wait_for_state(
            client,
            page,
            """(() => {
              const view = document.querySelector('[data-testid="kanban-board-view"]');
              const badges = view?.querySelectorAll('[data-testid="kanban-task-queued-badge"]') || [];
              return { ready: badges.length === 0, count: badges.length };
            })()""",
            timeout_sec=90.0,
        )
        assert zero_badges.get("count") == 0, zero_badges

        # Full loop: T3 really completes as well.
        t3_done = _api_wait_task_status(api_url, t3_id, "completed", timeout_sec=240.0)
        assert str(t3_done.get("result") or "").strip()


def _seed_kanban_closure_fixture(api_url: str) -> dict[str, object]:
    seeded = _http_json_write("POST", f"{api_url}/api/v1/chats/test/seed-kanban-closure-fixture")
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
@pytest.mark.timeout(600)
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

    warm_ui_route("/")
    if deep_link_path.startswith("/"):
        warm_ui_route(deep_link_path)

    with _open_chat_page_with_attach_retry(f"{ui_url}/{chat_id}") as (client, page):
        ensure_chat_route(client, page, target_url=f"{ui_url}/{chat_id}")
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

    board = _http_json_write(
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
            _open_kanban_board(client, page, board_id, board_name)

            add_ready = wait_for_state(
                client,
                page,
                """(() => {
                  const btn = document.querySelector('[data-testid="kanban-add-task-ready"]');
                  return { ready: !!btn };
                })()""",
                timeout_sec=90.0,
            )
            assert add_ready.get("ready") is True

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
            tasks = task_id.get("items") or []
            assert isinstance(tasks, list) and len(tasks) == 1
            persisted = tasks[0]
            assert str(persisted.get("model_override") or "") == chosen_model
            assert str(persisted.get("title") or "") == task_title
        finally:
            restore = (
                "localStorage.removeItem('kanban_last_board_id')"
                if previous_board is None
                else f"localStorage.setItem('kanban_last_board_id', {json.dumps(str(previous_board))})"
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

    board = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {"name": board_name, "description": "Chrome model override E2E"},
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    task = _http_json_write(
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
            _open_kanban_board(client, page, board_id, board_name)

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

            set_model = client.evaluate(
                page,
                """(async () => {
                  const drawer =
                    document.querySelector('[data-testid="kanban-task-drawer"]')
                    || document.querySelector('[role="dialog"]');
                  if (!drawer) return { ok: false, reason: 'no-drawer' };
                  const sel = Array.from(drawer.querySelectorAll('select')).find(
                    (s) => (s.className || '').includes('chart-2'),
                  );
                  if (!sel) return { ok: false, reason: 'no-select' };
                  const setter = Object.getOwnPropertyDescriptor(
                    HTMLSelectElement.prototype, 'value',
                  ).set;
                  setter.call(sel, '');
                  sel.dispatchEvent(new Event('change', { bubbles: true }));
                  // Wait two animation frames so React flushes the modelValue state
                  // update before the Save button closure is re-created.
                  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
                  return { ok: true, value: sel.value };
                })()""",
                timeout_sec=5.0,
            )
            assert set_model == {"ok": True, "value": ""}

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
                else f"localStorage.setItem('kanban_last_board_id', {json.dumps(str(previous_board))})"
            )
            client.evaluate(page, restore, timeout_sec=5.0)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_task_created_via_ui_form_with_skills() -> None:
    """Real-user flow: inline create form → skill picker → select skill → submit.

    Uses a real discoverable skill from the live backend (never mocked). The
    picker selection is driven through the actual Popover/Command UI, and the
    persisted task must carry the selected ``extra_skill_ids``.
    """
    marker = str(time.time_ns())
    board_name = f"Chrome Skills Board {marker}"
    task_title = f"Chrome Skills Task {marker}"
    api_url = get_e2e_api_url()

    board = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {"name": board_name, "description": "Chrome UI skill picker E2E"},
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    prebuilt_resp = http_json("GET", f"{api_url}/api/v1/skills?type=prebuilt&sort_by=name&order=asc")
    local_resp = http_json("GET", f"{api_url}/api/v1/skills?type=local&sort_by=name&order=asc")
    prebuilt = (prebuilt_resp.get("skills") if isinstance(prebuilt_resp, dict) else None) or []
    local = (local_resp.get("skills") if isinstance(local_resp, dict) else None) or []
    skills = [*prebuilt, *local]
    if not skills:
        pytest.skip("live backend exposes no discoverable skills; picker selection flow untestable")

    target = skills[0]
    target_id = str(target.get("id") or "")
    assert target_id

    with open_settings_subroute("/settings/kanban") as (client, page):
        previous_board = client.evaluate(
            page,
            "localStorage.getItem('kanban_last_board_id')",
            timeout_sec=5.0,
        )
        try:
            _open_kanban_board(client, page, board_id, board_name)

            wait_for_state(
                client,
                page,
                """(() => {
                  const btn = document.querySelector('[data-testid="kanban-add-task-ready"]');
                  return { ready: !!btn };
                })()""",
                timeout_sec=90.0,
            )
            client.evaluate(
                page,
                """(() => {
                  const btn = document.querySelector('[data-testid="kanban-add-task-ready"]');
                  if (!btn) return false;
                  btn.click();
                  return true;
                })()""",
                timeout_sec=5.0,
            )

            form_state = wait_for_state(
                client,
                page,
                """(() => {
                  const titleInput = document.querySelector(
                    'input[placeholder="Task title"], input[placeholder="任务标题"]',
                  );
                  const submit = document.querySelector('[data-testid="kanban-create-submit"]');
                  const picker = document.querySelector('[data-testid="kanban-skill-picker-trigger"]');
                  return { ready: !!titleInput && !!submit && !!picker, hasPicker: !!picker };
                })()""",
                timeout_sec=60.0,
            )
            assert form_state.get("hasPicker") is True

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

            opened = client.evaluate(
                page,
                """(() => {
                  const trigger = document.querySelector('[data-testid="kanban-skill-picker-trigger"]');
                  if (!trigger) return false;
                  trigger.click();
                  return true;
                })()""",
                timeout_sec=5.0,
            )
            assert opened is True

            searched = client.evaluate(
                page,
                f"""(() => {{
                  const input = document.querySelector(
                    'input[data-cmdk-input], input[cmdk-input]',
                  );
                  if (!input) return false;
                  const setter = Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype, 'value',
                  ).set;
                  setter.call(input, {target_id!r});
                  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                  return true;
                }})()""",
                timeout_sec=5.0,
            )
            assert searched is True

            selected = wait_for_state(
                client,
                page,
                """(() => {
                  const option = document.querySelector('[role="option"]');
                  if (!option) return { ready: false };
                  option.click();
                  return { ready: true, text: option.textContent || '' };
                })()""",
                timeout_sec=15.0,
            )
            assert selected.get("ready") is True

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

            persisted = http_json(
                "GET",
                f"{api_url}/api/v1/kanban/boards/{board_id}/tasks?status=ready",
            )
            assert isinstance(persisted, dict)
            tasks = persisted.get("items") or []
            assert isinstance(tasks, list) and len(tasks) == 1
            task = tasks[0]
            assert str(task.get("title") or "") == task_title
            assert target_id in (task.get("extra_skill_ids") or [])
        finally:
            restore = (
                "localStorage.removeItem('kanban_last_board_id')"
                if previous_board is None
                else f"localStorage.setItem('kanban_last_board_id', {json.dumps(str(previous_board))})"
            )
            client.evaluate(page, restore, timeout_sec=5.0)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_task_skill_drawer_edit_and_clear() -> None:
    """Drawer skill chips → edit mode → picker add/keep → save → persisted (real UI).

    Seeds a task with one real discoverable skill via REST, opens the drawer,
    enters skill edit mode through the chip row, adds a second skill through the
    picker when available (otherwise keeps the existing one), saves, and asserts
    the persisted ``extra_skill_ids`` reflect the drawer state.
    """
    marker = str(time.time_ns())
    board_name = f"Chrome Skills Edit Board {marker}"
    task_title = f"Chrome Skills Edit Task {marker}"
    file_id = f"chrome-e2e-skills-edit-{marker}"
    api_url = get_e2e_api_url()

    board = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {"name": board_name, "description": "Chrome UI skill drawer edit E2E"},
    )
    assert isinstance(board, dict)
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    prebuilt_resp = http_json("GET", f"{api_url}/api/v1/skills?type=prebuilt&sort_by=name&order=asc")
    local_resp = http_json("GET", f"{api_url}/api/v1/skills?type=local&sort_by=name&order=asc")
    prebuilt = (prebuilt_resp.get("skills") if isinstance(prebuilt_resp, dict) else None) or []
    local = (local_resp.get("skills") if isinstance(local_resp, dict) else None) or []
    skills = [*prebuilt, *local]
    if not skills:
        pytest.skip("live backend exposes no discoverable skills; drawer skill edit untestable")

    target_id = str(skills[0].get("id") or "")
    assert target_id
    add_id = str(skills[1].get("id") or "") if len(skills) > 1 else ""

    task = _http_json_write(
        "POST",
        f"{api_url}/api/v1/kanban/boards/{board_id}/tasks",
        {
            "title": task_title,
            "priority": "low",
            "initial_status": "ready",
            "extra_skill_ids": [target_id],
            "attachment_ids": [file_id],
        },
    )
    assert isinstance(task, dict)
    task_id = str(task.get("task_id") or task.get("id") or "")
    assert task_id
    assert target_id in (task.get("extra_skill_ids") or [])

    with open_settings_subroute("/settings/kanban") as (client, page):
        previous_board = client.evaluate(
            page,
            "localStorage.getItem('kanban_last_board_id')",
            timeout_sec=5.0,
        )
        try:
            _open_kanban_board(client, page, board_id, board_name)

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

            chips_state = wait_for_state(
                client,
                page,
                f"""(() => {{
                  const drawer =
                    document.querySelector('[data-testid="kanban-task-drawer"]')
                    || document.querySelector('[role="dialog"]');
                  const chip = Array.from(drawer?.querySelectorAll('span') || []).find(
                    (s) => (s.textContent || '').trim() === {target_id!r},
                  );
                  return {{ ready: !!drawer && !!chip, hasChip: !!chip }};
                }})()""",
                timeout_sec=90.0,
            )
            assert chips_state.get("hasChip") is True

            entered_edit = client.evaluate(
                page,
                f"""(() => {{
                  const drawer =
                    document.querySelector('[data-testid="kanban-task-drawer"]')
                    || document.querySelector('[role="dialog"]');
                  const chip = Array.from(drawer?.querySelectorAll('span') || []).find(
                    (s) => (s.textContent || '').trim() === {target_id!r},
                  );
                  if (!chip) return false;
                  chip.click();
                  return true;
                }})()""",
                timeout_sec=5.0,
            )
            assert entered_edit is True

            picker_state = wait_for_state(
                client,
                page,
                """(() => {
                  const drawer =
                    document.querySelector('[data-testid="kanban-task-drawer"]')
                    || document.querySelector('[role="dialog"]');
                  const trigger = drawer?.querySelector(
                    '[data-testid="kanban-skill-picker-trigger"]',
                  );
                  return { ready: !!trigger, hasTrigger: !!trigger };
                })()""",
                timeout_sec=60.0,
            )
            assert picker_state.get("hasTrigger") is True

            if add_id:
                opened = client.evaluate(
                    page,
                    """(() => {
                      const drawer =
                        document.querySelector('[data-testid="kanban-task-drawer"]')
                        || document.querySelector('[role="dialog"]');
                      const trigger = drawer?.querySelector(
                        '[data-testid="kanban-skill-picker-trigger"]',
                      );
                      if (!trigger) return false;
                      trigger.click();
                      return true;
                    })()""",
                    timeout_sec=5.0,
                )
                assert opened is True

                searched = client.evaluate(
                    page,
                    f"""(() => {{
                      const input = document.querySelector(
                        'input[data-cmdk-input], input[cmdk-input]',
                      );
                      if (!input) return false;
                      const setter = Object.getOwnPropertyDescriptor(
                        HTMLInputElement.prototype, 'value',
                      ).set;
                      setter.call(input, {add_id!r});
                      input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                      return true;
                    }})()""",
                    timeout_sec=5.0,
                )
                assert searched is True

                selected = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const option = document.querySelector('[role="option"]');
                      if (!option) return { ready: false };
                      option.click();
                      return { ready: true, text: option.textContent || '' };
                    })()""",
                    timeout_sec=15.0,
                )
                assert selected.get("ready") is True

            saved = client.evaluate(
                page,
                """(() => {
                  const drawer =
                    document.querySelector('[data-testid="kanban-task-drawer"]')
                    || document.querySelector('[role="dialog"]');
                  const save = drawer?.querySelector('[data-testid="kanban-save-skills"]');
                  if (!save) return false;
                  save.click();
                  return true;
                })()""",
                timeout_sec=5.0,
            )
            assert saved is True

            # Wait until the drawer exits skill-edit mode and shows the saved chips
            # (unlike raw text matching, this cannot pass while edit mode is active).
            final_state = wait_for_state(
                client,
                page,
                f"""(() => {{
                  const drawer =
                    document.querySelector('[data-testid="kanban-task-drawer"]')
                    || document.querySelector('[role="dialog"]');
                  if (!drawer) return {{ ready: false, editing: false, chips: [], detail: 'no drawer' }};
                  const editing = !!drawer.querySelector(
                    '[data-testid="kanban-save-skills"]',
                  );
                  const wanted = [{target_id!r}, {json.dumps(add_id)}].filter(Boolean);
                  const chips = Array.from(drawer.querySelectorAll('span'))
                    .map((s) => (s.textContent || '').trim())
                    .filter((t) => wanted.includes(t));
                  const ready = !editing && wanted.every((id) => chips.includes(id));
                  return {{ ready, editing, chips, detail: drawer.textContent.slice(0, 300) }};
                }})()""",
                timeout_sec=60.0,
            )
            assert final_state.get("ready") is True, f"drawer did not exit skill edit mode: {final_state}"

            fetched = http_json("GET", f"{api_url}/api/v1/kanban/tasks/{task_id}")
            assert isinstance(fetched, dict)
            persisted_ids = fetched.get("extra_skill_ids") or []
            assert target_id in persisted_ids
            if add_id:
                assert add_id in persisted_ids
        finally:
            restore = (
                "localStorage.removeItem('kanban_last_board_id')"
                if previous_board is None
                else f"localStorage.setItem('kanban_last_board_id', {json.dumps(str(previous_board))})"
            )
            client.evaluate(page, restore, timeout_sec=5.0)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_kanban_drawer_review_comment_thread_render() -> None:
    """Validate that Kanban Task Drawer renders structured ReviewCommentThread elements."""
    marker = str(time.time_ns())
    board_name = f"ReviewBoard {marker}"
    task_title = f"ReviewTask {marker}"
    api_url = get_e2e_api_url()
    board = _http_json_write("POST", f"{api_url}/api/v1/kanban/boards", {"name": board_name})
    board_id = str(board["board_id"])

    file_id = f"chrome-e2e-review-{marker}"
    task_payload = {
        "title": task_title,
        "description": "E2E verification review thread test",
        "completion_criteria": "Assert all criteria pass",
        "initial_status": "ready",
        "attachment_ids": [file_id],
        "metadata": {
            "acceptance_results": [
                {
                    "label": "Shell Acceptance Gate",
                    "passed": False,
                    "reason": "Test suite failed with 1 error",
                    "duration_ms": 142,
                    "comments": [
                        {
                            "id": "e2e-rev-1",
                            "severity": "critical",
                            "message": "Critical syntax error detected in service",
                            "target_path": "app/service.py",
                            "line_range": "45-50",
                            "fix_suggestion": "Add missing colon after if condition",
                        },
                        {
                            "id": "e2e-rev-2",
                            "severity": "warning",
                            "message": "Performance warning: slow DB lookup",
                            "target_path": "app/service.py",
                        },
                    ],
                }
            ]
        },
    }
    task = _http_json_write("POST", f"{api_url}/api/v1/kanban/boards/{board_id}/tasks", task_payload)
    task_id = str(task["task_id"])

    with open_settings_subroute("/settings/kanban") as (client, page):
        previous_board = client.evaluate(
            page,
            "localStorage.getItem('kanban_last_board_id')",
            timeout_sec=5.0,
        )
        try:
            _open_kanban_board(client, page, board_id, board_name)
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

            review_state = wait_for_state(
                client,
                page,
                """(() => {
                  const drawer = document.querySelector('[data-testid="kanban-task-drawer"]')
                    || document.querySelector('[role="dialog"]');
                  if (!drawer) return { ready: false, reason: 'no-drawer' };
                  const box = drawer.querySelector('[data-testid="review-comment-box"]');
                  const text = drawer.textContent || '';
                  const hasCrit = text.includes('Critical syntax error detected in service');
                  const hasPath = text.includes('app/service.py:45-50');
                  return {
                    ready: !!box && hasCrit && hasPath,
                    hasBox: !!box,
                    hasCrit,
                    hasPath,
                  };
                })()""",
                timeout_sec=30.0,
            )
            assert review_state.get("ready") is True, f"Review comment thread not properly rendered in Drawer: {review_state}"
        finally:
            restore = (
                "localStorage.removeItem('kanban_last_board_id')"
                if previous_board is None
                else f"localStorage.setItem('kanban_last_board_id', {json.dumps(str(previous_board))})"
            )
            client.evaluate(page, restore, timeout_sec=5.0)
