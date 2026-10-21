"""Persist post-replace snapshot_truncated into batch metadata."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.skills.replace.snapshot_honesty import persist_replace_snapshot_truncated_flag


@pytest.mark.asyncio
async def test_persist_skips_when_not_truncated() -> None:
    with patch("app.services.skill_optimization.bootstrap.get_skill_optimization_storage") as mock_boot:
        persist_replace_snapshot_truncated_flag("b1", "sid", snapshot_truncated=False)
        mock_boot.assert_not_called()


@pytest.mark.asyncio
async def test_persist_sets_metadata_flag() -> None:
    row = MagicMock()
    row.skill_metadata = {"batch_kind": "market_replace", "snapshot_truncated": False}
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    storage = MagicMock()
    storage._get_session.return_value.__aenter__ = AsyncMock(return_value=session)
    storage._get_session.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.skill_optimization.bootstrap.get_skill_optimization_storage",
        return_value=storage,
    ):
        await persist_replace_snapshot_truncated_flag("b1", "sid", snapshot_truncated=True)

    assert row.skill_metadata["snapshot_truncated"] is True
    session.commit.assert_awaited_once()
