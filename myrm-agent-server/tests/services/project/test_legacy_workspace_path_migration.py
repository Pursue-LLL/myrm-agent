"""Tests for clearing legacy auto-generated project workspace_path values."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text

from app.database.migrations import CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL
from app.database.models.project import Project
from app.platform_utils import get_session_factory


async def _insert_project(*, project_id: str, workspace_path: str | None) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Project(
                id=project_id,
                name=f"Legacy probe {project_id}",
                workspace_path=workspace_path,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


async def _fetch_workspace_path(project_id: str) -> str | None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        result = await db.execute(select(Project.workspace_path).where(Project.id == project_id))
        return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_legacy_project_workspace_path_migration_clears_fake_paths() -> None:
    fake_id = "legacyfake01"
    await _insert_project(
        project_id=fake_id,
        workspace_path="/persistent/workspace/project_legacyfake01",
    )

    session_factory = get_session_factory()
    async with session_factory() as db:
        await db.execute(text(CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL))
        await db.commit()

    assert await _fetch_workspace_path(fake_id) is None


@pytest.mark.asyncio
async def test_legacy_project_workspace_path_migration_preserves_real_bind() -> None:
    real_id = "realbind0001"
    bound_path = "/Users/alice/Obsidian/Research"
    await _insert_project(project_id=real_id, workspace_path=bound_path)

    session_factory = get_session_factory()
    async with session_factory() as db:
        await db.execute(text(CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL))
        await db.commit()

    assert await _fetch_workspace_path(real_id) == bound_path


@pytest.mark.asyncio
async def test_legacy_project_workspace_path_migration_preserves_other_persistent_paths() -> None:
    other_id = "persistws01"
    other_path = "/persistent/ws"
    await _insert_project(project_id=other_id, workspace_path=other_path)

    session_factory = get_session_factory()
    async with session_factory() as db:
        await db.execute(text(CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL))
        await db.commit()

    assert await _fetch_workspace_path(other_id) == other_path
