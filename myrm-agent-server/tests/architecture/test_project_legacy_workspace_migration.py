"""Architecture: legacy project workspace_path cleanup migration must stay registered."""

from __future__ import annotations

import pytest

from app.database.migrations import (
    CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL,
    MIGRATION_STATEMENTS,
)


@pytest.mark.architecture
def test_migration_clears_legacy_project_workspace_paths() -> None:
    assert CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL in MIGRATION_STATEMENTS
    assert MIGRATION_STATEMENTS[-1] == CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL
