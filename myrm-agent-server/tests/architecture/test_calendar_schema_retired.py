"""Architecture: calendar_events schema must stay dropped with no ORM surface."""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.architecture
def test_migration_tail_drops_calendar_events_table() -> None:
    from app.database import migrations

    assert migrations.MIGRATION_STATEMENTS[-1] == "DROP TABLE IF EXISTS calendar_events"


@pytest.mark.architecture
def test_index_tail_drops_calendar_events_indexes() -> None:
    from app.database import migrations

    stmts = migrations.INDEX_STATEMENTS
    assert "DROP INDEX IF EXISTS idx_calendar_events_start_at" in stmts
    assert "DROP INDEX IF EXISTS idx_calendar_events_agent_id" in stmts
    assert "DROP INDEX IF EXISTS idx_calendar_events_status" in stmts
    assert stmts[-2:] == [
        "CREATE INDEX IF NOT EXISTS idx_artifact_publications_artifact_id ON artifact_publications(artifact_id)",
        "CREATE INDEX IF NOT EXISTS idx_artifact_publications_target_id ON artifact_publications(hosting_target_id)",
    ]


@pytest.mark.architecture
def test_no_calendar_orm_or_api_packages_on_disk() -> None:
    app_root = _SERVER_ROOT / "app"
    assert not (app_root / "api" / "calendar").exists()
    assert not (app_root / "core" / "calendar").exists()
    models_dir = app_root / "database" / "models"
    assert not (models_dir / "calendar_event.py").exists()
