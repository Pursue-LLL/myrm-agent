"""Tests for provider-backed integration skill gates (x-live-search).

Requirement-based gates (env keys, CLI binaries) are covered by ``test_requirements_availability.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.skills.gates.oauth_availability import (
    X_LIVE_SEARCH_SKILL_ID,
    X_LIVE_SEARCH_UNAVAILABLE,
    apply_integration_oauth_availability,
)
from app.core.skills.models import Skill
from app.core.storage.types import SkillType


def _x_live_search_skill() -> Skill:
    return Skill(
        id=X_LIVE_SEARCH_SKILL_ID,
        type=SkillType.PREBUILT,
        name="x-live-search",
        description="test",
        storage_path="skills/prebuilt/x-live-search",
        available=True,
    )


@pytest.mark.asyncio
async def test_x_live_search_marked_unavailable_without_xai_provider() -> None:
    skill = _x_live_search_skill()

    with patch(
        "app.core.skills.gates.oauth_availability._is_xai_provider_configured",
        new_callable=AsyncMock,
        return_value=False,
    ):
        await apply_integration_oauth_availability([skill], AsyncMock())

    assert skill.available is False
    assert skill.unavailable_reason == X_LIVE_SEARCH_UNAVAILABLE


@pytest.mark.asyncio
async def test_x_live_search_stays_available_with_xai_provider() -> None:
    skill = _x_live_search_skill()

    with patch(
        "app.core.skills.gates.oauth_availability._is_xai_provider_configured",
        new_callable=AsyncMock,
        return_value=True,
    ):
        await apply_integration_oauth_availability([skill], AsyncMock())

    assert skill.available is True
    assert skill.unavailable_reason is None
