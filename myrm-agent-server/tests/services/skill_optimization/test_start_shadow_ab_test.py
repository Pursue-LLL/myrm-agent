"""Tests for start_shadow_ab_test (shadow A/B startup shared by evolution + API)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.skills.optimization.types import (
    ABTestResult,
    ABTestStatus,
    SkillQualityScore,
    SkillVersion,
)

from app.services.skill_optimization.skill_version_sync import start_shadow_ab_test


def _quality_score() -> SkillQualityScore:
    return SkillQualityScore(
        success_rate=0.8,
        token_efficiency=0.7,
        execution_time=0.75,
        user_satisfaction=0.85,
        call_frequency=0.5,
    )


def _active_version(skill_id: str, version: int, content: str) -> SkillVersion:
    return SkillVersion(
        skill_id=skill_id,
        version=version,
        content=content,
        quality_score=_quality_score(),
        created_at=datetime(2026, 1, 1),
        created_by="test",
        optimization_id=None,
        is_active=True,
        metadata=None,
    )


def _running_ab_row(skill_id: str) -> MagicMock:
    row = MagicMock()
    row.skill_id = skill_id
    return row


@pytest.mark.asyncio
async def test_start_shadow_ab_test_persists_inactive_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    skill_id = "demo-skill"
    baseline_content = "# Baseline"
    candidate_content = "# Candidate"
    active = _active_version(skill_id, 2, baseline_content)

    storage = MagicMock()
    storage.get_active_version = AsyncMock(return_value=active)
    storage.get_latest_quality = AsyncMock(return_value=_quality_score())
    storage.save_ab_test = AsyncMock()

    monkeypatch.setattr(
        "app.services.skill_optimization.skill_version_sync._assert_no_running_ab_test",
        AsyncMock(),
    )

    persist_mock = AsyncMock(return_value=_active_version(skill_id, 3, candidate_content))
    monkeypatch.setattr(
        "app.services.skill_optimization.skill_version_sync.persist_skill_version",
        persist_mock,
    )

    ab_result = ABTestResult(
        skill_id=skill_id,
        baseline_version=2,
        candidate_version=3,
        baseline_score=_quality_score(),
        candidate_score=_quality_score(),
        sample_size=0,
        status=ABTestStatus.RUNNING,
        started_at=datetime(2026, 6, 1),
    )

    mock_engine = MagicMock()
    mock_engine.start_ab_test = AsyncMock(return_value=ab_result)

    with patch(
        "myrm_agent_harness.agent.skills.optimization.ABTestEngine",
        return_value=mock_engine,
    ):
        result = await start_shadow_ab_test(storage, skill_id, candidate_content)

    persist_mock.assert_awaited_once()
    _args, call_kwargs = persist_mock.await_args
    assert _args[2] == candidate_content
    assert call_kwargs["activate"] is False
    assert call_kwargs["sync_disk"] is False
    assert call_kwargs["version"] == 3
    storage.save_ab_test.assert_awaited_once_with(ab_result)
    assert result["skill_id"] == skill_id
    assert result["baseline_version"] == 2
    assert result["candidate_version"] == 3
    assert result["status"] == ABTestStatus.RUNNING.value
    assert result["test_id"] == f"{skill_id}:v2:v3"


@pytest.mark.asyncio
async def test_start_shadow_ab_test_rejects_duplicate_running() -> None:
    skill_id = "busy-skill"
    storage = MagicMock()
    running_row = _running_ab_row(skill_id)
    ab_repo = MagicMock()
    ab_repo.get_running_tests = AsyncMock(return_value=[running_row])
    session = MagicMock()

    @asynccontextmanager
    async def _session_ctx():
        yield session

    storage._get_session = _session_ctx

    with patch(
        "app.adapters.skill_optimization.ab_test_repo.ABTestRepository",
        return_value=ab_repo,
    ):
        with pytest.raises(ValueError, match="already running"):
            await start_shadow_ab_test(storage, skill_id, "# Candidate")


@pytest.mark.asyncio
async def test_start_shadow_ab_test_does_not_sync_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    skill_id = "disk-skill"
    active = _active_version(skill_id, 1, "# Active")

    storage = MagicMock()
    storage.get_active_version = AsyncMock(return_value=active)
    storage.get_latest_quality = AsyncMock(return_value=None)
    storage.save_ab_test = AsyncMock()

    monkeypatch.setattr(
        "app.services.skill_optimization.skill_version_sync._assert_no_running_ab_test",
        AsyncMock(),
    )

    sync_disk = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.services.skill_optimization.skill_version_sync.sync_content_to_disk",
        sync_disk,
    )

    persist_mock = AsyncMock(return_value=_active_version(skill_id, 2, "# Candidate"))
    monkeypatch.setattr(
        "app.services.skill_optimization.skill_version_sync.persist_skill_version",
        persist_mock,
    )

    ab_result = ABTestResult(
        skill_id=skill_id,
        baseline_version=1,
        candidate_version=2,
        baseline_score=_quality_score(),
        candidate_score=_quality_score(),
        sample_size=0,
        status=ABTestStatus.RUNNING,
        started_at=datetime(2026, 6, 1),
    )
    mock_engine = MagicMock()
    mock_engine.start_ab_test = AsyncMock(return_value=ab_result)

    with patch(
        "myrm_agent_harness.agent.skills.optimization.ABTestEngine",
        return_value=mock_engine,
    ):
        await start_shadow_ab_test(storage, skill_id, "# Candidate")

    sync_disk.assert_not_awaited()
