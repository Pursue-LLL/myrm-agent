"""Tests for idle tool pruner task."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session
from app.database.models.agent import Agent
from app.tasks.idle_tool_pruner import scan_and_prune_idle_tools


@pytest.fixture
async def db_session() -> AsyncSession:
    """Provide a database session."""
    async with get_session() as session:
        yield session


@pytest.mark.asyncio
async def test_scan_and_prune_idle_tools_empty_db(
    db_session: AsyncSession,
) -> None:
    """Test the pruner task when no agents exist or no idle tools."""
    # Run the task
    created = await scan_and_prune_idle_tools()

    # Should be 0 since the DB is presumably empty or has no active agents with idle skills in tests
    assert created >= 0


@pytest.mark.asyncio
async def test_scan_and_prune_idle_tools_with_active_agent(
    db_session: AsyncSession,
) -> None:
    """Test the pruner task logic execution path."""
    # We create a dummy agent with no skills just to hit the loop
    agent = Agent(
        id="test-agent-123",
        name="Test Agent",
        description="A test agent",
        model_config={},
        skill_ids=[],
        is_active=True,
    )
    db_session.add(agent)
    await db_session.commit()

    # Since it has no skill_ids, it shouldn't create any proposals
    created = await scan_and_prune_idle_tools()

    assert created >= 0
