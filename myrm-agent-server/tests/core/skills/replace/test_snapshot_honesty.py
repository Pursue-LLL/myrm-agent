"""Post-replace snapshot honesty assessment."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.skills.replace.snapshot_honesty import assess_post_replace_snapshot_honesty


@pytest.mark.asyncio
async def test_honesty_true_when_binary_present_after_install() -> None:
    with patch("app.core.skills.store.service.skills_service") as mock_svc:
        mock_svc.list_skill_files = AsyncMock(return_value=["SKILL.md", "assets/logo.png"])
        assert await assess_post_replace_snapshot_honesty(
            "local::demo",
            pre_collect_truncated=False,
            snapshotted_resource_paths=frozenset(),
        )


@pytest.mark.asyncio
async def test_honesty_false_when_only_snapshotted_text_files() -> None:
    with patch("app.core.skills.store.service.skills_service") as mock_svc:
        mock_svc.list_skill_files = AsyncMock(return_value=["SKILL.md", "scripts/run.py"])
        assert not await assess_post_replace_snapshot_honesty(
            "local::demo",
            pre_collect_truncated=False,
            snapshotted_resource_paths=frozenset({"scripts/run.py"}),
        )


@pytest.mark.asyncio
async def test_honesty_true_when_text_file_not_in_snapshot() -> None:
    with patch("app.core.skills.store.service.skills_service") as mock_svc:
        mock_svc.list_skill_files = AsyncMock(return_value=["SKILL.md", "refs/extra.md"])
        assert await assess_post_replace_snapshot_honesty(
            "local::demo",
            pre_collect_truncated=False,
            snapshotted_resource_paths=frozenset(),
        )
