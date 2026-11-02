"""Real Chrome MCP E2E: a finished shell job that left a program running offers a stop button in the panel.

The seed job ends at once and leaves a long-lived child in its process group. The panel must say so, and the stop
button must stop that child (checked from the process table, not from the response alone). The same row must stay
legible in both themes and inside a panel narrower than the one phones get.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.support.chrome_background_panel import (
    MIN_TEXT_CONTRAST,
    background_tasks_panel,
    measure_contrast,
    measure_narrow_panel,
    stop_leftover_from_panel,
    wait_api_row,
    wait_for_leftover_hint,
    wait_marker_gone,
    wait_until_leftover_gone,
)
from tests.support.chrome_mcp_e2e import get_e2e_api_url, http_json
from tests.support.marked_command_lines import processes_with_marker


@contextmanager
def _seeded_leftover_task(api_base: str) -> Iterator[tuple[str, str]]:
    """A finished shell job whose child is still running, as (task_id, marker); the job is stopped through the API on exit."""
    seed = http_json("POST", f"{api_base}/api/v1/background-tasks/test/seed-shell-fixture?mode=leftover")
    assert isinstance(seed, dict)
    task_id = str(seed["task_id"])
    marker = str(seed["leftover_marker"])
    try:
        wait_api_row(api_base, task_id, leftover=1)
        assert len(processes_with_marker(marker)) == 1
        yield task_id, marker
    finally:
        http_json(
            "POST",
            f"{api_base}/api/v1/background-tasks/{task_id}/cancel",
            expected_statuses=frozenset({200, 201, 400}),
        )


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(300)
def test_background_tasks_panel_stops_what_a_finished_shell_job_left_running() -> None:
    api_base = get_e2e_api_url()
    with _seeded_leftover_task(api_base) as (task_id, marker), background_tasks_panel(api_base) as (client, page):
        wait_for_leftover_hint(client, page)

        stop_leftover_from_panel(client, page)

        wait_marker_gone(marker)
        wait_api_row(api_base, task_id, leftover=0)
        wait_until_leftover_gone(client, page)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(300)
def test_background_tasks_leftover_controls_are_legible_in_both_themes_and_fit_a_narrow_panel() -> None:
    api_base = get_e2e_api_url()
    with _seeded_leftover_task(api_base), background_tasks_panel(api_base) as (client, page):
        wait_for_leftover_hint(client, page)

        for theme in ("dark", "light"):
            for part, contrast in measure_contrast(client, page, theme).items():
                assert contrast["ratio"] >= MIN_TEXT_CONTRAST, f"{part} in {theme}: {contrast}"

        narrow = measure_narrow_panel(client, page)
        assert narrow["hintInside"] is True and narrow["stopInside"] is True, narrow
        assert narrow["overflowX"] <= 1, narrow
