"""Tests for runtime skill ID resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.backends.skills.local_skill_id import local_skill_id_from_path

from app.core.skills.effective_skill_ids import resolve_runtime_skill_ids
from app.core.skills.models import UserSkillConfig


@pytest.mark.asyncio
async def test_returns_explicit_profile_allowlist_when_non_empty() -> None:
    result = await resolve_runtime_skill_ids(["prebuilt::web-search", "local::abc"])
    assert result == ["prebuilt::web-search", "local::abc"]


@pytest.mark.asyncio
async def test_empty_profile_returns_empty_list_wysiwyg() -> None:
    """WYSIWYG: empty or None profile returns 0 skills, no silent fallback."""
    result_empty = await resolve_runtime_skill_ids([])
    assert result_empty == []

    result_none = await resolve_runtime_skill_ids(None)
    assert result_none == []


@pytest.mark.asyncio
async def test_migrates_legacy_name_based_local_ids_in_explicit_profile(tmp_path: Path) -> None:
    skill_dir = tmp_path / "legacy-skill"
    skill_dir.mkdir()
    legacy_id = "local::legacy-skill"
    expected_id = local_skill_id_from_path(skill_dir)

    config = UserSkillConfig(user_id="test-user", local_skill_paths=[str(tmp_path)])
    with patch(
        "app.core.skills.effective_skill_ids.skills_service.user_config.get_config",
        new=AsyncMock(return_value=config),
    ):
        result = await resolve_runtime_skill_ids([legacy_id, "prebuilt::web-search"])

    assert result == [expected_id, "prebuilt::web-search"]
