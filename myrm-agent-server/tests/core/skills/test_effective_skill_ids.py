"""Tests for runtime skill ID resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from pathlib import Path

from myrm_agent_harness.backends.skills.local_skill_id import local_skill_id_from_path

from app.core.skills.effective_skill_ids import resolve_runtime_skill_ids
from app.core.skills.models import UserSkillConfig


@pytest.mark.asyncio
async def test_returns_explicit_profile_allowlist_when_non_empty() -> None:
    result = await resolve_runtime_skill_ids(["prebuilt::web-search", "local::abc"])
    assert result == ["prebuilt::web-search", "local::abc"]


@pytest.mark.asyncio
async def test_empty_profile_falls_back_to_user_enabled_catalog() -> None:
    config = UserSkillConfig(
        user_id="test-user",
        enabled_prebuilt_ids=["prebuilt::summarize"],
        enabled_local_skill_ids=["local::deadbeef01234567"],
    )
    with patch(
        "app.core.skills.effective_skill_ids.skills_service.user_config.get_config",
        new=AsyncMock(return_value=config),
    ):
        result = await resolve_runtime_skill_ids([])

    assert result == ["prebuilt::summarize", "local::deadbeef01234567"]


@pytest.mark.asyncio
async def test_deduplicates_enabled_ids_preserving_order() -> None:
    config = UserSkillConfig(
        user_id="test-user",
        enabled_prebuilt_ids=["prebuilt::a"],
        enabled_local_skill_ids=["prebuilt::a", "local::1"],
    )
    with patch(
        "app.core.skills.effective_skill_ids.skills_service.user_config.get_config",
        new=AsyncMock(return_value=config),
    ):
        result = await resolve_runtime_skill_ids(None)

    assert result == ["prebuilt::a", "local::1"]


@pytest.mark.asyncio
async def test_migrates_legacy_name_based_local_ids(tmp_path: Path) -> None:
    skill_dir = tmp_path / "legacy-skill"
    skill_dir.mkdir()
    legacy_id = "local::legacy-skill"
    expected_id = local_skill_id_from_path(skill_dir)

    config = UserSkillConfig(user_id="test-user", enabled_local_skill_ids=[legacy_id])
    with (
        patch(
            "app.core.skills.effective_skill_ids._LOCAL_INSTALL_DIR",
            tmp_path,
        ),
        patch(
            "app.core.skills.effective_skill_ids.skills_service.user_config.get_config",
            new=AsyncMock(return_value=config),
        ),
        patch(
            "app.core.skills.effective_skill_ids.skills_service.user_config.save_config",
            new=AsyncMock(),
        ) as save_mock,
    ):
        result = await resolve_runtime_skill_ids([])

    assert result == [expected_id]
    save_mock.assert_awaited_once()
    saved = save_mock.await_args.args[0]
    assert saved.enabled_local_skill_ids == [expected_id]
