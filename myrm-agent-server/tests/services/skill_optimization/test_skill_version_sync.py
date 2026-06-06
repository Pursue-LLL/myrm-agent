"""Unit tests for skill version dual-write helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.skill_optimization.skill_version_sync import atomic_write_text_file


def test_atomic_write_text_file_replaces_content(tmp_path: Path) -> None:
    target = tmp_path / "SKILL.md"
    target.write_text("v1", encoding="utf-8")

    atomic_write_text_file(target, "v2")

    assert target.read_text(encoding="utf-8") == "v2"


def test_atomic_write_text_file_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "SKILL.md"

    atomic_write_text_file(target, "fresh")

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
