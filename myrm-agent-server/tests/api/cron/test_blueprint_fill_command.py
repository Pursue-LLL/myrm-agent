"""Test blueprint fill exposes router command for read_it_later."""

from __future__ import annotations

from app.core.cron.blueprints import fill_blueprint


def test_fill_read_it_later_includes_sync_command() -> None:
    result = fill_blueprint("read_it_later", {"time": "06:00", "weekdays": "everyday"})
    assert result is not None
    assert result.command == "__wiki_source_sync__"
