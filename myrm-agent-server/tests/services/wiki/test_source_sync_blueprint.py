"""Tests for read_it_later blueprint router migration."""

from __future__ import annotations

from app.core.cron.blueprints import fill_blueprint, get_blueprint


class TestReadItLaterBlueprint:
    def test_job_type_is_router_with_sync_command(self) -> None:
        bp = get_blueprint("read_it_later")
        assert bp is not None
        assert bp.job_defaults.job_type == "router"
        assert bp.job_defaults.command == "__wiki_source_sync__"

    def test_fill_exposes_router_command(self) -> None:
        result = fill_blueprint("read_it_later", {"time": "06:00", "weekdays": "everyday"})
        assert result is not None
        assert result.job_type == "router"
        assert result.command == "__wiki_source_sync__"
