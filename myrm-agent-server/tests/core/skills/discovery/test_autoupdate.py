"""Unit tests for the skill auto-update checker.

Covers cooldown caching, force refresh, empty-installed handling, update
detection via version comparison, singleton accessor, and quarantine-install
delegation.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.backends.skills.types_metadata import SkillMetadata

from app.core.skills.discovery.autoupdate import (
    SkillAutoUpdateChecker,
    SkillUpdateInfo,
    UpdateCheckResult,
    get_update_checker,
)


def test_update_check_result_properties() -> None:
    """has_updates/available_updates must reflect the update flags."""
    result = UpdateCheckResult(
        updates=[
            SkillUpdateInfo("a", "1.0.0", "1.1.0", "github", "id-a", True),
            SkillUpdateInfo("b", "1.0.0", "1.0.0", "github", "id-b", False),
        ]
    )
    assert result.has_updates is True
    assert [u.skill_name for u in result.available_updates] == ["a"]


def test_empty_updates_has_no_updates() -> None:
    result = UpdateCheckResult()
    assert result.has_updates is False
    assert result.available_updates == []


@pytest.mark.asyncio
async def test_cooldown_returns_cached_result() -> None:
    """Checks within the cooldown window must not re-query installed skills."""
    checker = SkillAutoUpdateChecker()
    cached = UpdateCheckResult(checked_at=time.time())
    checker._last_check = cached

    with patch("app.core.skills.store.service.skills_service") as mock_skills:
        result = await checker.check_updates("user-1")

    assert result is cached
    mock_skills.list_skills.assert_not_called()


@pytest.mark.asyncio
async def test_force_bypasses_cooldown() -> None:
    """force=True must re-run the query even inside the cooldown window."""
    checker = SkillAutoUpdateChecker()
    cached = UpdateCheckResult(checked_at=time.time())
    checker._last_check = cached

    from app.core.skills.marketplace.market_service import market_service

    with (
        patch("app.core.skills.store.service.skills_service") as mock_skills,
        patch.object(market_service._base, "_sources", []),
    ):
        mock_skills.list_skills = AsyncMock(return_value=[])
        result = await checker.check_updates("user-1", force=True)

    assert result is not cached
    mock_skills.list_skills.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_installed_returns_empty_result() -> None:
    """No installed skills must yield an empty result and update the cache."""
    checker = SkillAutoUpdateChecker()

    with patch("app.core.skills.store.service.skills_service") as mock_skills:
        mock_skills.list_skills = AsyncMock(return_value=[])
        result = await checker.check_updates("user-1")

    assert result.updates == []
    assert checker._last_check is result


@pytest.mark.asyncio
async def test_update_detected_via_version_compare() -> None:
    """A remote newer version must be reported as an available update."""
    skill = SkillMetadata(name="demo_skill", description="demo", version="1.0.1")
    checker = SkillAutoUpdateChecker()

    detail = MagicMock()
    detail.version = "2.0.0"
    detail.id = "id-demo"
    source = MagicMock(source_name="github")
    source.get_detail = AsyncMock(return_value=detail)

    from app.core.skills.marketplace.market_service import market_service

    with (
        patch.object(market_service._base, "_sources", [source]),
        patch("app.core.skills.store.service.skills_service") as mock_skills,
        patch(
            "myrm_agent_harness.agent.skills.market.helpers.read_origin",
            return_value={},
        ),
        patch(
            "myrm_agent_harness.agent.skills.market.service.LOCAL_INSTALL_DIR",
            Path("/tmp/skills-installed"),
        ),
    ):
        mock_skills.list_skills = AsyncMock(return_value=[skill])
        result = await checker.check_updates("user-1")

    assert len(result.updates) == 1
    assert result.updates[0].has_update is True
    assert result.updates[0].current_version == "1.0.1"
    assert result.updates[0].remote_version == "2.0.0"


@pytest.mark.asyncio
async def test_update_skill_delegates_to_quarantine_install() -> None:
    """update_skill must forward to market_service.install."""
    info = SkillUpdateInfo("a", "1.0.0", "1.1.0", "github", "id-a", True)

    with patch(
        "app.core.skills.marketplace.market_service.market_service.install",
        new=AsyncMock(return_value=MagicMock()),
    ) as mock_install:
        checker = SkillAutoUpdateChecker()
        await checker.update_skill(info, "user-1")

    mock_install.assert_awaited_once_with(skill_id="id-a", source="github")


def test_get_update_checker_singleton() -> None:
    """get_update_checker must return the same instance across calls."""
    from app.core.skills.discovery import autoupdate as au

    au._checker = None
    first = get_update_checker()
    second = get_update_checker()
    assert first is second
    au._checker = None
