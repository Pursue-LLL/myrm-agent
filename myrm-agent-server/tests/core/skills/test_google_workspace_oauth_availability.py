"""Tests for integration OAuth availability on prebuilt skills."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills.models import Skill
from app.core.skills.oauth_availability import (
    GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE,
    GOOGLE_WORKSPACE_SKILL_ID,
    apply_integration_oauth_availability,
)


def _google_workspace_skill() -> Skill:
    return Skill(
        id=GOOGLE_WORKSPACE_SKILL_ID,
        type=SkillType.PREBUILT,
        name="Google Workspace",
        description="Calendar, Gmail, Drive",
        storage_path="skills/prebuilt/google-workspace",
    )


@pytest.mark.asyncio
async def test_apply_oauth_availability_marks_google_workspace_unavailable() -> None:
    skill = _google_workspace_skill()
    db = AsyncMock()

    with patch(
        "app.core.skills.oauth_availability.is_google_workspace_oauth_connected",
        AsyncMock(return_value=False),
    ):
        await apply_integration_oauth_availability([skill], db)

    assert skill.available is False
    assert skill.unavailable_reason == GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE


@pytest.mark.asyncio
async def test_apply_oauth_availability_leaves_connected_skill_available() -> None:
    skill = _google_workspace_skill()
    db = AsyncMock()

    with patch(
        "app.core.skills.oauth_availability.is_google_workspace_oauth_connected",
        AsyncMock(return_value=True),
    ):
        await apply_integration_oauth_availability([skill], db)

    assert skill.available is True
    assert skill.unavailable_reason is None


@pytest.mark.asyncio
async def test_apply_oauth_availability_skips_unrelated_skills() -> None:
    other = Skill(
        id="daily-briefing",
        type=SkillType.PREBUILT,
        name="Daily Briefing",
        description="Morning briefing",
        storage_path="skills/prebuilt/daily-briefing",
    )
    db = AsyncMock()

    with patch(
        "app.core.skills.oauth_availability.is_google_workspace_oauth_connected",
        AsyncMock(return_value=False),
    ) as connected_mock:
        await apply_integration_oauth_availability([other], db)

    connected_mock.assert_not_awaited()
    assert other.available is True
