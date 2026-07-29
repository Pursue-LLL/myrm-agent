"""Unit tests for discovery_adopt."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.skills.discovery_adopt import complete_discovery_adoption


@pytest.mark.asyncio
async def test_adoption_no_op_when_allowlist_empty() -> None:
    agent = type("Agent", (), {"skills": []})()
    with patch(
        "app.core.skills.discovery_adopt.AgentService.get_agent_by_id",
        new=AsyncMock(return_value=agent),
    ):
        result = await complete_discovery_adoption(
            "builtin-general",
            "systematic-debugging",
        )

    assert result.allowlist_appended is False


@pytest.mark.asyncio
async def test_adoption_appends_when_explicit_allowlist_omits_skill() -> None:
    agent = type("Agent", (), {"skills": ["code-review"]})()
    update_agent = AsyncMock(return_value=agent)
    with (
        patch(
            "app.core.skills.discovery_adopt.AgentService.get_agent_by_id",
            new=AsyncMock(return_value=agent),
        ),
        patch(
            "app.core.skills.discovery_adopt.AgentService.update_agent",
            new=update_agent,
        ),
    ):
        result = await complete_discovery_adoption(
            "builtin-general",
            "systematic-debugging",
        )

    assert result.allowlist_appended is True
    assert result.agent_id == "builtin-general"
    update_agent.assert_awaited_once()
    merged = update_agent.await_args.args[1].skill_ids
    assert merged == ["code-review", "systematic-debugging"]


@pytest.mark.asyncio
async def test_adoption_no_op_when_skill_already_in_allowlist() -> None:
    agent = type("Agent", (), {"skills": ["systematic-debugging"]})()
    update_agent = AsyncMock()
    with (
        patch(
            "app.core.skills.discovery_adopt.AgentService.get_agent_by_id",
            new=AsyncMock(return_value=agent),
        ),
        patch(
            "app.core.skills.discovery_adopt.AgentService.update_agent",
            new=update_agent,
        ),
    ):
        result = await complete_discovery_adoption(
            "builtin-general",
            "systematic-debugging",
        )

    assert result.allowlist_appended is False
    update_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_adoption_logs_and_no_ops_when_update_fails() -> None:
    agent = type("Agent", (), {"skills": ["code-review"]})()
    with (
        patch(
            "app.core.skills.discovery_adopt.AgentService.get_agent_by_id",
            new=AsyncMock(return_value=agent),
        ),
        patch(
            "app.core.skills.discovery_adopt.AgentService.update_agent",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await complete_discovery_adoption(
            "builtin-general",
            "systematic-debugging",
        )

    assert result.allowlist_appended is False
    assert result.allowlist_append_error == (
        "Failed to update agent skill allowlist after install"
    )
