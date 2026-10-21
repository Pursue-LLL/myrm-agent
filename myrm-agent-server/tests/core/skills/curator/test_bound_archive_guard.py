"""Manual archive must refuse skills bound by agents or cron jobs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.core.skills.curator.bound_skills import SkillBoundError
from app.core.skills.curator.service import SkillPinnedError, archive_skill_with_guards


@pytest.mark.asyncio
async def test_archive_skill_with_guards_refuses_bound_skill(tmp_path: Path) -> None:
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\n---\n", encoding="utf-8")

    with (
        patch("app.core.skills.curator.service.resolve_skill_path", return_value=skill_dir),
        patch(
            "app.core.skills.curator.service.assert_skill_not_bound_for_archive",
            AsyncMock(side_effect=SkillBoundError("demo-skill")),
        ),
    ):
        with pytest.raises(SkillBoundError):
            await archive_skill_with_guards("demo-skill")


@pytest.mark.asyncio
async def test_archive_skill_with_guards_honors_pin(tmp_path: Path) -> None:
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\n---\n", encoding="utf-8")
    (skill_dir / ".stats.json").write_text('{"pinned": true}', encoding="utf-8")

    with (
        patch("app.core.skills.curator.service.resolve_skill_path", return_value=skill_dir),
        patch("app.core.skills.curator.service.assert_skill_not_bound_for_archive", AsyncMock()),
        patch("app.core.skills.curator.service.get_stats_collector"),
    ):
        with pytest.raises(SkillPinnedError):
            await archive_skill_with_guards("demo-skill")
