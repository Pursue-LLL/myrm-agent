"""Integration-style tests for skill version activate + disk sync."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.skill_optimization.skill_version_sync import (
    activate_version_with_disk_sync,
    persist_skill_version,
)
from myrm_agent_harness.agent.skills.optimization.types import SkillQualityScore, SkillVersion


def _sample_version(skill_id: str, version: int, content: str) -> SkillVersion:
    return SkillVersion(
        skill_id=skill_id,
        version=version,
        content=content,
        quality_score=SkillQualityScore(
            success_rate=0.9,
            token_efficiency=0.8,
            execution_time=0.7,
            user_satisfaction=0.85,
            call_frequency=0.6,
        ),
        created_at=datetime(2026, 1, 1),
        created_by="test",
        optimization_id=None,
        is_active=False,
        metadata=None,
    )


@pytest.mark.asyncio
async def test_activate_version_with_disk_sync_writes_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    skill_id = "demo-skill"
    content_v1 = "# Skill v1"
    storage = MagicMock()
    storage.get_skill_version = AsyncMock(return_value=_sample_version(skill_id, 1, content_v1))
    storage.activate_version = AsyncMock(return_value=_sample_version(skill_id, 1, content_v1))

    skill_md = tmp_path / "SKILL.md"

    async def _resolve(_skill_id: str) -> Path:
        return skill_md

    monkeypatch.setattr(
        "app.services.skill_optimization.skill_version_sync.resolve_skill_md_path",
        _resolve,
    )
    monkeypatch.setattr(
        "app.services.skill_optimization.skill_version_sync.bump_skill_config_version",
        lambda: None,
        raising=False,
    )
    import app.core.skills.config_version as cv

    monkeypatch.setattr(cv, "bump_skill_config_version", lambda: None)

    await activate_version_with_disk_sync(storage, skill_id, 1)

    assert skill_md.read_text(encoding="utf-8") == content_v1
    storage.activate_version.assert_awaited_once_with(skill_id, 1)


@pytest.mark.asyncio
async def test_persist_skill_version_retries_once(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = MagicMock()
    saved = _sample_version("s1", 1, "body")
    storage.list_skill_versions = AsyncMock(return_value=[])
    storage.save_skill_version = AsyncMock(side_effect=[RuntimeError("db locked"), saved])
    storage.activate_version = AsyncMock(return_value=saved)

    monkeypatch.setattr(
        "app.services.skill_optimization.skill_version_sync.sync_content_to_disk",
        AsyncMock(return_value=True),
    )

    result = await persist_skill_version(storage, "s1", "body", sync_disk=False)

    assert result.version == 1
    assert storage.save_skill_version.await_count == 2
