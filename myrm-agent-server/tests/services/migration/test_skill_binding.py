"""Tests for competitor skill binding to agent profiles."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.migration.skill_binding import bind_local_skill_names_to_agent


@pytest.mark.asyncio()
async def test_bind_appends_new_skill_names() -> None:
    profile = MagicMock()
    profile.skills = ["existing"]

    with (
        patch(
            "app.services.migration.skill_binding.AgentService.get_agent_by_id",
            new=AsyncMock(return_value=profile),
        ),
        patch(
            "app.services.migration.skill_binding.AgentService.update_agent",
            new=AsyncMock(return_value=MagicMock()),
        ) as update_mock,
    ):
        bound = await bind_local_skill_names_to_agent("agent-1", ["lint", "existing"])

    assert bound == 1
    update_mock.assert_awaited_once()
