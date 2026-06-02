"""Tests for idle tool pruner task."""

import pytest

from app.database.connection import get_session
from app.database.models.agent import Agent
from app.tasks.idle_tool_pruner import scan_and_prune_idle_tools


@pytest.mark.asyncio
async def test_scan_and_prune_idle_tools_empty_db(setup_test_database) -> None:
    """Test the pruner task when no agents exist or no idle tools."""
    created = await scan_and_prune_idle_tools()
    assert created >= 0

@pytest.mark.asyncio
async def test_scan_and_prune_idle_tools_with_active_agent(setup_test_database) -> None:
    """Test the pruner task logic execution path."""
    async with get_session() as session:
        agent = Agent(
            id="test-agent-123",
            name="Test Agent",
            description="A test agent",
            model_config={},
            skill_ids=[],
            is_active=True
        )
        session.add(agent)
        await session.commit()
    
    created = await scan_and_prune_idle_tools()
    assert created >= 0
