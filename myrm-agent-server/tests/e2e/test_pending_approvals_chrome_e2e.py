"""Real Chrome E2E: Fleet pendingApprovals KPI reflects kanban IN_REVIEW.

Seeds IN_REVIEW tasks directly in the live server DB (the state is only
reachable after a real agent completes a require_approval run; a UI probe
cannot dispatch a live agent), then verifies the /agents Fleet "Pending" KPI
ticks up in the real UI and falls back after both real REST transitions:
approve (IN_REVIEW -> COMPLETED) and reject (IN_REVIEW -> READY).

Every UI assertion is anchored by an independent API-level reading of the same
metric, so a wrong DB path or a broken aggregation is diagnosed immediately
instead of surfacing as a confusing UI-only diff. Incremental assertions
(N -> N+1 -> N) immunize against concurrent activity from other developers
sharing the server.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)

# Reads the /agents Fleet "Pending" KPI. Stays not-ready until the label match
# AND a rendered value are both present, so the baseline read cannot race the
# fleet-overview fetch (the KPI card only mounts once the API has answered).
# Diagnostic fields (href/appLayout/cards/apiBase) are attached to the not-ready
# state so a timeout surfaces the real DOM condition instead of a bare diff.
_PENDING_KPI_JS = """(() => {
  const appLayout = !!document.querySelector('[data-testid="app-layout"]');
  const cards = [...document.querySelectorAll('div.rounded-lg.border.p-3')]
    .map(c => ({
      label: c.querySelector('p.text-xs')?.textContent?.trim() ?? null,
      value: c.querySelector('p.text-lg')?.textContent?.trim() ?? null,
    }));
  const pending = cards.find(c => c.label && /pend|待审批/i.test(c.label));
  if (!pending) {
    return {
      ready: false,
      text: '',
      href: location.href,
      appLayout,
      cards,
      apiBase: window.__MYRM_E2E_API_BASE__ ?? null,
    };
  }
  const text = (pending.value ?? '').trim();
  return {
    ready: text !== '',
    text,
    href: location.href,
    appLayout,
    cards,
    apiBase: window.__MYRM_E2E_API_BASE__ ?? null,
  };
})()"""


def _probe_sqlite(
    db_path: str, sql: str, params: tuple[object, ...] = ()
) -> bool:
    """Run a read probe against a possibly WAL-mode SQLite DB.

    The shared E2E backend keeps `data.db` in WAL mode. A fresh connection can
    only see rows committed after the last checkpoint when it can access the
    `-shm` index; forcing `journal_mode=WAL` on connect rebuilds that index for
    this reader. Without it a board seeded milliseconds earlier can be
    invisible, which surfaces as a bogus "live DB not found" failure.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=15.0, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=15000")
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.Error:
                # Read-only file or a foreign lock; fall back to whatever
                # snapshot is visible through the existing -shm index.
                pass
            return conn.execute(sql, params).fetchone() is not None
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def _real_user_home() -> Path:
    """Real login home (Cursor redirects HOME for spawned processes)."""
    try:
        import pwd

        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError, OSError):
        return Path.home()


def _private_runtime_data_dir(api_url: str) -> Path | None:
    """Map a PRIVATE E2E API port to its isolated runtime data dir.

    The dev-gate allocator registers every isolated backend in
    `~/.local/state/myrm-isolated/registry.json` keyed by backendPort. The
    shared stack (:8080) is not a registered runtime and returns None.
    """
    if not api_url:
        return None
    try:
        port = int(urlsplit(api_url).port or 0)
    except ValueError:
        return None
    if not port or port == 8080:
        return None
    registry = _real_user_home() / ".local/state/myrm-isolated/registry.json"
    if not registry.is_file():
        return None
    try:
        payload = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    records = payload.get("runtimes") if isinstance(payload, dict) else None
    if not isinstance(records, dict):
        return None
    for record in records.values():
        if not isinstance(record, dict):
            continue
        if record.get("backendPort") == port:
            data_dir = record.get("dataDir")
            if isinstance(data_dir, str) and data_dir:
                return Path(data_dir)
    return None


def _resolve_live_db_path(board_id: str, api_url: str) -> str:
    """Resolve the server's SQLite path by matching the just-created board.

    In PRIVATE mode the pytest process talks to an isolated backend whose DB
    lives under the isolated runtime data dir (registered by dev-gate keyed on
    backendPort); the shared :8080 stack is probed by candidate instead. Every
    candidate that owns the kanban schema is probed for the board created
    through the API — the DB containing it is the live one. Each candidate is
    retried a few times because the board was committed into the WAL only
    moments ago and a WAL read can lag a checkpoint cycle.
    """
    candidates: list[Path] = []
    private_data_dir = _private_runtime_data_dir(api_url)
    if private_data_dir is not None:
        candidates.append(private_data_dir / "data.db")
    data_dir = os.environ.get("MYRM_DATA_DIR")
    if data_dir:
        candidates.append(Path(data_dir) / "data.db")
    from app.config.settings import settings

    candidates.append(Path(settings.database.sqlite_path).expanduser())
    candidates.append(Path("/Users/yululiu/.myrm/data.db"))
    candidates.append(Path.home() / ".myrm" / "data.db")

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        has_schema = _probe_sqlite(
            key,
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='kanban_boards'",
        )
        if not has_schema:
            continue
        for attempt in range(3):
            if _probe_sqlite(
                key,
                "SELECT 1 FROM kanban_boards WHERE id = ?",
                (board_id,),
            ):
                return key
            if attempt < 2:
                time.sleep(1.0)
    env_hint = {
        "MYRM_DATA_DIR": os.environ.get("MYRM_DATA_DIR", ""),
        "MYRM_E2E_PRIVATE_RUNTIME_ID": os.environ.get(
            "MYRM_E2E_PRIVATE_RUNTIME_ID", ""
        ),
        "E2E_API_BASE": os.environ.get("E2E_API_BASE", ""),
    }
    raise RuntimeError(
        f"live kanban DB not found for board {board_id}; api_url={api_url} "
        f"env={env_hint} probed={sorted(seen)}"
    )


def _api_pending_approvals(api_url: str) -> int:
    """Server-side pendingApprovals (goal approvals + kanban IN_REVIEW)."""
    body = http_json("GET", f"{api_url}/api/v1/statistics/badges")
    return int(body["data"]["pendingApprovals"])


def _read_pending_kpi(
    client: object, page: object, *, timeout_sec: float = 90.0
) -> str:
    """Read the /agents Fleet 'Pending' KPI value (blocks until it renders)."""
    state = wait_for_state(client, page, _PENDING_KPI_JS, timeout_sec=timeout_sec)
    return str(state.get("text") or "")


def _seed_in_review(db_path: str, task_id: str, board_id: str, title: str) -> None:
    """Insert an IN_REVIEW task directly in the server DB.

    The server keeps this DB in WAL mode, so the writer must use WAL too —
    otherwise its commit can leave the WAL in a state the server's readers
    cannot see. Explicit close matters as well: a live sqlite3 writer keeps the
    WAL index pinned, so never hold the connection across the API assertions.
    """
    conn = sqlite3.connect(db_path, timeout=15.0)
    try:
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "INSERT INTO kanban_tasks "
            "(id, board_id, title, description, status, priority, retry_count, "
            "max_retries, consecutive_failures, result, error, created_at, "
            "updated_at, goal_mode, require_approval) "
            "VALUES (?, ?, ?, '', 'in_review', 'normal', 0, 3, 0, '', '', "
            "datetime('now'), datetime('now'), 0, 1)",
            (task_id, board_id, title),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
def test_fleet_pending_approvals_kpi_tracks_kanban_in_review() -> None:
    marker = str(time.time_ns())
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    board = http_json(
        "POST",
        f"{api_url}/api/v1/kanban/boards",
        {"name": f"E2E Fleet KPI Board {marker}"},
    )
    board_id = str(board.get("board_id") or board.get("id") or "")
    assert board_id

    warm_ui_route("/agents")

    approve_task_id = f"fleetkpi-apr-{marker}"
    reject_task_id = f"fleetkpi-rej-{marker}"
    db_path = _resolve_live_db_path(board_id, api_url)

    try:
        with open_mcp_page(f"{ui_url}/agents") as (client, page):
            # Baseline: the KPI card must be rendered, so 'before' is a digit.
            before = _read_pending_kpi(client, page)
            assert before.isdigit(), f"Pending KPI not rendered; before={before!r}"
            api_before = _api_pending_approvals(api_url)

            def assert_after_seed(task_id: str, title: str) -> None:
                # Seed AFTER the baseline read; seeding earlier would make N
                # already include the task and the N -> N+1 delta never appear.
                _seed_in_review(db_path, task_id, board_id, title)
                seeded_ok = False
                for attempt in range(3):
                    if _probe_sqlite(
                        db_path,
                        "SELECT 1 FROM kanban_tasks WHERE id = ?",
                        (task_id,),
                    ):
                        seeded_ok = True
                        break
                    if attempt < 2:
                        time.sleep(1.0)
                actual = _api_pending_approvals(api_url)
                assert seeded_ok, f"IN_REVIEW seed failed for {task_id}"
                assert actual == api_before + 1, (
                    f"badges API must count the seeded IN_REVIEW task: "
                    f"api_before={api_before} actual={actual} db_path={db_path}"
                )
                seeded = wait_for_state(client, page, _PENDING_KPI_JS, timeout_sec=90.0)
                seeded_text = str(seeded.get("text") or "")
                assert seeded_text == str(int(before) + 1), (
                    f"KPI should tick +1 after IN_REVIEW seed: before={before} "
                    f"seeded={seeded_text}"
                )

            def assert_after_release(action_label: str) -> None:
                assert _api_pending_approvals(api_url) == api_before, (
                    f"badges API must fall back after {action_label}: "
                    f"api_before={api_before}"
                )
                settled = wait_for_state(
                    client, page, _PENDING_KPI_JS, timeout_sec=90.0
                )
                settled_text = str(settled.get("text") or "")
                assert settled_text == before, (
                    f"KPI should fall back after {action_label}: before={before!r} "
                    f"settled={settled_text!r}"
                )

            # Lifecycle 1: IN_REVIEW -> approve -> COMPLETED releases the KPI.
            assert_after_seed(approve_task_id, f"E2E Fleet KPI Task {marker}")
            approved = http_json(
                "POST",
                f"{api_url}/api/v1/kanban/tasks/{approve_task_id}/approve",
                {"approver": "e2e-operator"},
            )
            assert str(approved.get("status") or "") == "completed"
            assert_after_release("approve")

            # Lifecycle 2: IN_REVIEW -> reject -> READY also releases the KPI.
            assert_after_seed(reject_task_id, f"E2E Fleet KPI Reject Task {marker}")
            rejected = http_json(
                "POST",
                f"{api_url}/api/v1/kanban/tasks/{reject_task_id}/reject",
                {"reason": "e2e reject", "approver": "e2e-operator"},
            )
            assert str(rejected.get("status") or "") == "ready"
            assert_after_release("reject")
    finally:
        conn = sqlite3.connect(db_path, timeout=15.0)
        try:
            conn.execute("PRAGMA busy_timeout=15000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "DELETE FROM kanban_tasks WHERE id IN (?, ?)",
                (approve_task_id, reject_task_id),
            )
            conn.commit()
        finally:
            conn.close()
