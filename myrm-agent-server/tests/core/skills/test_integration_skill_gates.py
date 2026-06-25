"""Tests for integration skill availability gates (x-live-search, notion, linear)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills.models import Skill
from app.core.skills.oauth_availability import (
    LINEAR_PROJECT_SKILL_ID,
    NOTION_WORKSPACE_SKILL_ID,
    X_LIVE_SEARCH_SKILL_ID,
    X_LIVE_SEARCH_UNAVAILABLE,
    XURL_BIN_UNAVAILABLE,
    XURL_SKILL_ID,
    apply_integration_oauth_availability,
)


@pytest.mark.asyncio
async def test_x_live_search_marked_unavailable_without_xai_provider() -> None:
    skill = Skill(
        id=X_LIVE_SEARCH_SKILL_ID,
        type=SkillType.PREBUILT,
        name="x-live-search",
        description="test",
        storage_path="skills/prebuilt/x-live-search",
        available=True,
    )
    db = AsyncMock()

    with patch(
        "app.core.skills.oauth_availability._is_xai_provider_configured",
        new_callable=AsyncMock,
        return_value=False,
    ):
        await apply_integration_oauth_availability([skill], db)

    assert skill.available is False
    assert skill.unavailable_reason == X_LIVE_SEARCH_UNAVAILABLE


@pytest.mark.asyncio
async def test_notion_marked_unavailable_without_env() -> None:
    skill = Skill(
        id=NOTION_WORKSPACE_SKILL_ID,
        type=SkillType.PREBUILT,
        name="notion-workspace",
        description="test",
        storage_path="skills/prebuilt/notion-workspace",
        available=True,
    )
    db = AsyncMock()

    with patch(
        "app.core.skills.oauth_availability._is_skill_env_configured",
        new_callable=AsyncMock,
        return_value=False,
    ):
        await apply_integration_oauth_availability([skill], db)

    assert skill.available is False
    assert skill.unavailable_reason is not None


@pytest.mark.asyncio
async def test_linear_available_when_env_configured() -> None:
    skill = Skill(
        id=LINEAR_PROJECT_SKILL_ID,
        type=SkillType.PREBUILT,
        name="linear-project",
        description="test",
        storage_path="skills/prebuilt/linear-project",
        available=True,
    )
    db = AsyncMock()

    with patch(
        "app.core.skills.oauth_availability._is_skill_env_configured",
        new_callable=AsyncMock,
        return_value=True,
    ):
        await apply_integration_oauth_availability([skill], db)

    assert skill.available is True


@pytest.mark.asyncio
async def test_xurl_marked_unavailable_without_cli() -> None:
    skill = Skill(
        id=XURL_SKILL_ID,
        type=SkillType.PREBUILT,
        name="xurl",
        description="test",
        storage_path="skills/prebuilt/xurl",
        available=True,
    )
    db = AsyncMock()

    with patch(
        "app.core.skills.oauth_availability._are_skill_bins_available",
        return_value=False,
    ):
        await apply_integration_oauth_availability([skill], db)

    assert skill.available is False
    assert skill.unavailable_reason == XURL_BIN_UNAVAILABLE
