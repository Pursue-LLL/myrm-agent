"""Unit tests for disabled_skill_roots collection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills.disabled_skill_roots import collect_disabled_skill_roots
from app.core.skills.models import Skill


@pytest.mark.asyncio
async def test_collect_disabled_skill_roots_excludes_enabled() -> None:
    enabled_prebuilt = Skill(
        id="enabled-skill",
        name="Enabled",
        description="enabled",
        type=SkillType.PREBUILT,
        storage_path="/skills/enabled",
    )
    disabled_prebuilt = Skill(
        id="disabled-skill",
        name="Disabled",
        description="disabled",
        type=SkillType.PREBUILT,
        storage_path="/skills/disabled",
    )

    mock_config = MagicMock()
    mock_config.enabled_prebuilt_ids = ["enabled-skill"]
    mock_config.enabled_local_skill_ids = []

    mock_service = MagicMock()
    mock_service.list_skills = AsyncMock(return_value=[enabled_prebuilt, disabled_prebuilt])

    with (
        patch("app.core.skills.disabled_skill_roots.get_storage_provider"),
        patch(
            "app.core.skills.disabled_skill_roots.UserSkillConfigManager",
        ) as mock_config_cls,
        patch(
            "app.core.skills.disabled_skill_roots.SkillsService",
            return_value=mock_service,
        ),
    ):
        mock_config_cls.return_value.get_config = AsyncMock(return_value=mock_config)
        roots = await collect_disabled_skill_roots()

    assert roots == ["/skills/disabled"]


@pytest.mark.asyncio
async def test_collect_disabled_skill_roots_returns_empty_on_list_failure() -> None:
    mock_config = MagicMock()
    mock_config.enabled_prebuilt_ids = []
    mock_config.enabled_local_skill_ids = []

    mock_service = MagicMock()
    mock_service.list_skills = AsyncMock(side_effect=RuntimeError("db down"))

    with (
        patch("app.core.skills.disabled_skill_roots.get_storage_provider"),
        patch(
            "app.core.skills.disabled_skill_roots.UserSkillConfigManager",
        ) as mock_config_cls,
        patch(
            "app.core.skills.disabled_skill_roots.SkillsService",
            return_value=mock_service,
        ),
    ):
        mock_config_cls.return_value.get_config = AsyncMock(return_value=mock_config)
        roots = await collect_disabled_skill_roots()

    assert roots == []
