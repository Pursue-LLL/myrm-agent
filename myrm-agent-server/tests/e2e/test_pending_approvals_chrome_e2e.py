"""Real Chrome E2E: Fleet pendingApprovals KPI reflects kanban IN_REVIEW.

Seeds an IN_REVIEW task directly in the live server DB (the state is only
reachable after a real agent completes a require_approval run; a UI probe
cannot dispatch a live agent), then verifies the /agents Fleet "Pending" KPI
ticks up in the real UI and falls back after a real REST approve.

Incremental assertions (N -> N+1 -> N) immunize against concurrent activity
from other developers sharing the same dev server.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)


def _live_db_path() -> str:
    """Resolve the live server's SQLite path (the DB actually serving :8080).

    The pytest process shares the dev server's environment, but its imported
    settings may resolve to a different state dir; probe the real candidates
    and pick the one that actually owns the kanban tables.
    """
    candidates: list[Path] = []
    data_dir = os.environ.get("MYRM_DATA_DIR")
    if data_dir:
        candidates.append(Path(data_dir) / "data.db")
    from app.config.settings import settings

    candidates.append(Path(settings.database.sqlite_path).expanduser())
    candidates.append(Path.home() / ".myrm" / "data.db")

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            with sqlite3.connect(key, timeout=5.0) as conn:
                has = conn.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name='kanban_tasks'"
                ).fetchone()
        except sqlite3.Error:
            continue
        if has:
            return key
    raise RuntimeError(f"live kanban DB not found; probed {sorted(seen)}")


def _read_pending_kpi(client: object, page: object) -> str:
    """Read the /agents Fleet 'Pending' KPI value ('' while unknown)."""
    state = wait_for_state(
        client,
        page,
        """(() => {
          if (!document.querySelector('[data-testid="app-layout"]')) {
            return { ready: false, text: '' };
          }
          const cards = [...document.querySelectorAll('div.rounded-lg.border.p-3')];
          for (const card of cards) {
            const labelEl = card.querySelector('p.text-xs');
            if (labelEl && /pend|待审批/i.test(labelEl.textContent || '')) {
              const valEl = card.querySelector('p.text-lg');
              return { ready: true, text: valEl ? valEl.textContent.trim() : '' };
            }
          }
          return { ready: true, text: '' };
        })()""",
    )
    return str(state.get("text") or "")


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
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

    task_id = f"fleetkpi-{marker}"
    db_path = _live_db_path()
    with sqlite3.connect(db_path, timeout=15.0) as conn:
        conn.execute(
            "INSERT INTO kanban_tasks "
            "(id, board_id, title, description, status, priority, retry_count, "
            "max_retries, consecutive_failures, result, error, created_at, "
            "updated_at, goal_mode, require_approval) "
            "VALUES (?, ?, ?, '', 'in_review', 'normal', 0, 3, 0, '', '', "
            "datetime('now'), datetime('now'), 0, 1)",
            (task_id, board_id, f"E2E Fleet KPI Task {marker}"),
        )

    try:
        with open_mcp_page(f"{ui_url}/agents") as (client, page):
            before = _read_pending_kpi(client, page)

            seeded = wait_for_state(
                client,
                page,
                """(() => {
                  if (!document.querySelector('[data-testid="app-layout"]')) {
                    return { ready: false, text: '' };
                  }
                  const cards = [...document.querySelectorAll('div.rounded-lg.border.p-3')];
                  for (const card of cards) {
                    const labelEl = card.querySelector('p.text-xs');
                    if (labelEl && /pend|待审批/i.test(labelEl.textContent || '')) {
                      const valEl = card.querySelector('p.text-lg');
                      return { ready: true, text: valEl ? valEl.textContent.trim() : '' };
                    }
                  }
                  return { ready: true, text: '' };
                })()""",
            )
            seeded_text = str(seeded.get("text") or "")
            if before:
                assert seeded_text == str(int(before) + 1), (
                    f"KPI should tick +1 after IN_REVIEW seed: before={before} seeded={seeded_text}"
                )
            else:
                assert seeded_text.isdigit() and int(seeded_text) >= 1, (
                    f"KPI should appear after IN_REVIEW seed: before={before!r} seeded={seeded_text!r}"
                )

            approved = http_json(
                "POST",
                f"{api_url}/api/v1/kanban/tasks/{task_id}/approve",
                {"approver": "e2e-operator"},
            )
            assert str(approved.get("status") or "") == "completed"

            settled = wait_for_state(
                client,
                page,
                """(() => {
                  if (!document.querySelector('[data-testid="app-layout"]')) {
                    return { ready: false, text: '' };
                  }
                  const cards = [...document.querySelectorAll('div.rounded-lg.border.p-3')];
                  for (const card of cards) {
                    const labelEl = card.querySelector('p.text-xs');
                    if (labelEl && /pend|待审批/i.test(labelEl.textContent || '')) {
                      const valEl = card.querySelector('p.text-lg');
                      return { ready: true, text: valEl ? valEl.textContent.trim() : '' };
                    }
                  }
                  return { ready: true, text: '' };
                })()""",
            )
            settled_text = str(settled.get("text") or "")
            assert settled_text == before, (
                f"KPI should fall back after approve: before={before!r} settled={settled_text!r}"
            )
    finally:
        with sqlite3.connect(db_path, timeout=15.0) as conn:
            conn.execute("DELETE FROM kanban_tasks WHERE id = ?", (task_id,))
