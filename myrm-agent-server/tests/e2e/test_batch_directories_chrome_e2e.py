"""Real Chrome MCP E2E for Batch Directory project detail rendering.

Covers the user-visible surface of BatchDirectoryParallelPromptRunner:
- detail page renders project name / status badge / id / config (incl. Duration row)
- detail page renders resolved duration and directory chips after a terminal state
- list page shows the created project with aggregated status

Setup follows the kanban Chrome E2E pattern: create data through the real REST
API (shared / isolated backend), then open the UI route and assert on stable
``data-testid`` hooks. The batch project uses a temporary directory and
``notify_enabled=false`` so no channel notification is attempted.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_CREATED_DIRS: set[str] = set()


@pytest.fixture(autouse=True)
def _cleanup_batch_dirs() -> Iterator[None]:
    """Remove temporary directories created by this test process after each test."""
    yield
    _cleanup_temp_dirs()


def _unique_dir() -> str:
    """Create a real temporary directory on the backend host (same machine)."""
    base = "/tmp"
    path = os.path.join(base, f"myrm-bd-e2e-{uuid.uuid4().hex[:10]}")
    os.makedirs(path, exist_ok=True)
    _CREATED_DIRS.add(path)
    return path


def _http_json_write(
    method: str,
    url: str,
    body: dict[str, object] | None = None,
    *,
    attempts: int = 10,
) -> dict[str, object]:
    """Run a state-changing request tolerating transient shared-SQLite 5xx.

    A 500 here means the write transaction was rolled back before commit, so
    re-issuing the same payload is safe. Mirrors the kanban Chrome E2E helper.
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


def _create_project(api_url: str, *, notify_enabled: bool = False) -> dict[str, object]:
    """Create a batch project via the real REST API and return its detail."""
    marker = uuid.uuid4().hex[:8]
    return _http_json_write(
        "POST",
        f"{api_url}/api/v1/batch-directories",
        {
            "name": f"BD Chrome E2E {marker}",
            "prompt": "Reply with a single line: OK",
            "directories": [_unique_dir()],
            "concurrency": 1,
            "notify_enabled": notify_enabled,
        },
    )


def _cleanup_temp_dirs() -> None:
    """Remove only the temporary directories created by this test process."""
    import shutil

    for path in tuple(_CREATED_DIRS):
        try:
            shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
        _CREATED_DIRS.discard(path)


def _wait_terminal(api_url: str, project_id: str, *, timeout_sec: float = 90.0) -> dict[str, object]:
    """Poll the project until it reaches a terminal status."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        resp = http_json("GET", f"{api_url}/api/v1/batch-directories/{project_id}")
        assert isinstance(resp, dict)
        status = str(resp.get("status") or "")
        if status in {"completed", "failed", "cancelled"}:
            return resp
        time.sleep(3.0)
    raise AssertionError(f"Batch project {project_id} did not reach terminal state")


def _delete_project(api_url: str, project_id: str, *, timeout_sec: float = 120.0) -> None:
    """Cancel any running tasks, wait for terminal state, then delete.

    ``delete_project`` refuses while a task is still non-terminal, so teardown
    must first cancel (project flips to ``cancelled`` and running tasks are
    archived) and then retry the DELETE until the task archive settles.
    """
    http_json("POST", f"{api_url}/api/v1/batch-directories/{project_id}/cancel")
    _wait_terminal(api_url, project_id, timeout_sec=timeout_sec)
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            http_json(
                "DELETE",
                f"{api_url}/api/v1/batch-directories/{project_id}",
                expected_statuses=frozenset({204}),
            )
            return
        except RuntimeError as exc:
            if "still has running tasks" not in str(exc):
                raise
            time.sleep(2.0)
    raise AssertionError(f"Batch project {project_id} tasks did not settle before delete")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(360)
def test_batch_directory_detail_page_renders_project() -> None:
    """Detail page shows project name, id, status badge, config and directories."""
    api_url = get_e2e_api_url()
    created = _create_project(api_url)
    project_id = str(created.get("project_id") or "")
    assert project_id
    name = str(created.get("name") or "")
    try:
        detail_route = f"/batch-directories/{project_id}"
        warm_ui_route(detail_route)
        detail_url = f"{get_e2e_ui_url().rstrip('/')}{detail_route}"
        with open_mcp_page(detail_url) as (client, page):
            state = wait_for_state(
                client,
                page,
                """(() => {
                  const name = document.querySelector('[data-testid="bd-project-name"]');
                  const status = document.querySelector('[data-testid="bd-project-status"]');
                  const duration = document.querySelector('[data-testid="bd-config-duration-value"]');
                  const dirs = document.querySelector('[data-testid="bd-directories-card"]');
                  return {
                    ready: !!name && !!status && !!dirs,
                    nameText: name?.textContent || '',
                    statusText: status?.textContent || '',
                    durationText: duration?.textContent || '',
                    dirsText: dirs?.textContent || '',
                  };
                })()""",
                timeout_sec=60.0,
            )
            assert bool(state.get("ready"))
            assert name in str(state.get("nameText") or "")
            assert str(state.get("statusText") or "") != ""
            assert str(state.get("durationText") or "") != ""
            assert str(state.get("dirsText") or "")
    finally:
        _delete_project(api_url, project_id)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(420)
def test_batch_directory_terminal_state_renders_duration() -> None:
    """After a deterministic terminal state, the detail page shows the resolved
    duration and directory chips.

    The real agent may take minutes to complete the trivial prompt, so we do
    not wait for natural completion. Instead we cancel the project: cancel
    atomically flips the project to ``cancelled`` (a terminal state) and
    archives the running task, which lets teardown delete cleanly. The
    failure-marking branch of the directory chips is covered by backend
    integration tests.
    """
    api_url = get_e2e_api_url()
    created = _create_project(api_url)
    project_id = str(created.get("project_id") or "")
    assert project_id
    try:
        http_json("POST", f"{api_url}/api/v1/batch-directories/{project_id}/cancel")
        terminal = _wait_terminal(api_url, project_id, timeout_sec=60.0)
        assert str(terminal.get("status") or "") == "cancelled"
        detail_route = f"/batch-directories/{project_id}"
        warm_ui_route(detail_route)
        detail_url = f"{get_e2e_ui_url().rstrip('/')}{detail_route}"
        with open_mcp_page(detail_url) as (client, page):
            state = wait_for_state(
                client,
                page,
                """(() => {
                  const status = document.querySelector('[data-testid="bd-project-status"]');
                  const duration = document.querySelector('[data-testid="bd-config-duration-value"]');
                  const dirs = document.querySelector('[data-testid="bd-directories-card"]');
                  return {
                    ready: !!status && !!dirs,
                    statusText: status?.textContent || '',
                    durationText: duration?.textContent || '',
                    dirsText: dirs?.textContent || '',
                  };
                })()""",
                timeout_sec=60.0,
            )
            assert bool(state.get("ready"))
            assert str(state.get("statusText") or "") != ""
            assert str(state.get("durationText") or "") != ""
            assert str(state.get("durationText") or "") != "—"
            assert str(state.get("dirsText") or "")
    finally:
        _delete_project(api_url, project_id)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(360)
def test_batch_directory_list_page_shows_created_project() -> None:
    """List page shows the created project row with its name."""
    api_url = get_e2e_api_url()
    created = _create_project(api_url)
    project_id = str(created.get("project_id") or "")
    assert project_id
    name = str(created.get("name") or "")
    try:
        list_route = "/batch-directories"
        warm_ui_route(list_route)
        list_url = f"{get_e2e_ui_url().rstrip('/')}{list_route}"
        with open_mcp_page(list_url) as (client, page):
            state = wait_for_state(
                client,
                page,
                """(() => {
                  const rows = [...document.querySelectorAll('[data-testid="bd-project-row-name"]')];
                  const text = rows.map((r) => r?.textContent || '').join('|');
                  return { ready: rows.length > 0, text };
                })()""",
                timeout_sec=60.0,
            )
            assert bool(state.get("ready"))
            assert name in str(state.get("text") or "")
    finally:
        _delete_project(api_url, project_id)
