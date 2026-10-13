"""Manifest snapshot collector bounds and SKILL.md requirement."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.skills.replace.manifest_snapshot import collect_manifest_snapshot_contents


@pytest.mark.asyncio
async def test_collect_manifest_snapshot_requires_skill_md() -> None:
    with patch("app.core.skills.store.service.skills_service") as mock_svc:
        mock_svc.get_skill_file = AsyncMock(return_value=None)
        mock_svc.list_skill_files = AsyncMock(return_value=[])
        with pytest.raises(FileNotFoundError):
            await collect_manifest_snapshot_contents("local::demo")


@pytest.mark.asyncio
async def test_collect_manifest_snapshot_includes_resources() -> None:
    with patch("app.core.skills.store.service.skills_service") as mock_svc:
        mock_svc.get_skill_file = AsyncMock(
            side_effect=lambda _sid, path: {
                "SKILL.md": b"# Demo",
                "scripts/run.py": b"print('ok')",
            }.get(path),
        )
        mock_svc.list_skill_files = AsyncMock(return_value=["SKILL.md", "scripts/run.py"])
        md, resources, truncated = await collect_manifest_snapshot_contents("local::demo")
        assert md == "# Demo"
        assert resources == {"scripts/run.py": "print('ok')"}
        assert truncated is False
