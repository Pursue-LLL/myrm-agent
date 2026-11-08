"""Architecture: canvas schema and data dir must stay dropped with no ORM surface."""

from __future__ import annotations

from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent


def test_migration_drops_canvas_table() -> None:
    from app.database import migrations

    assert "DROP TABLE IF EXISTS canvas" in migrations.MIGRATION_STATEMENTS


def test_no_canvas_orm_or_api_packages_on_disk() -> None:
    app_root = _SERVER_ROOT / "app"
    assert not (app_root / "api" / "canvas").exists()
    assert not (app_root / "services" / "canvas").exists()
    models_dir = app_root / "database" / "models"
    assert not (models_dir / "canvas.py").exists()
