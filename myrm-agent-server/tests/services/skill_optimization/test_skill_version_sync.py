"""Unit tests for skill version dual-write helpers."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.skill_optimization.skill_version_sync import sync_content_to_disk


@pytest.fixture
def unregistered_skill() -> Iterator[None]:
    """The skills service knows no such skill, so the sync takes the local-disk path."""
    service = AsyncMock()
    service.get_skill.return_value = None
    with patch("app.core.skills.store.service.skills_service", service):
        yield


@pytest.fixture
def config_version_bump() -> Iterator[MagicMock]:
    with patch("app.core.skills.config_version.bump_skill_config_version") as bump:
        yield bump


@pytest.mark.asyncio
@pytest.mark.usefixtures("unregistered_skill")
async def test_sync_replaces_the_skill_file_and_bumps_the_config_version(tmp_path: Path, config_version_bump: MagicMock) -> None:
    target = tmp_path / "SKILL.md"
    target.write_text("v1", encoding="utf-8")

    assert await sync_content_to_disk("demo-skill", "v2", disk_path=target) is True

    assert target.read_text(encoding="utf-8") == "v2"
    config_version_bump.assert_called_once_with()


@pytest.mark.asyncio
@pytest.mark.usefixtures("unregistered_skill", "config_version_bump")
async def test_sync_creates_missing_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "SKILL.md"

    assert await sync_content_to_disk("demo-skill", "fresh", disk_path=target) is True

    assert target.read_text(encoding="utf-8") == "fresh"


@pytest.mark.asyncio
async def test_next_version_number_starts_at_one() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.services.skill_optimization.skill_version_sync import next_version_number

    storage = MagicMock()
    storage.list_skill_versions = AsyncMock(return_value=[])

    assert await next_version_number(storage, "demo-skill") == 1


@pytest.mark.asyncio
async def test_next_version_number_increments_from_latest() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.services.skill_optimization.skill_version_sync import next_version_number

    latest = MagicMock()
    latest.version = 4
    storage = MagicMock()
    storage.list_skill_versions = AsyncMock(return_value=[latest])

    assert await next_version_number(storage, "demo-skill") == 5
