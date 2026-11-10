"""The cron configuration the server hands the scheduler."""

from __future__ import annotations

from app.core.cron.adapters.setup import _build_cron_config


def test_server_runs_three_jobs_at_a_time() -> None:
    assert _build_cron_config().max_concurrent == 3
