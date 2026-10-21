"""Tests for AgentRepository.list_profiles and count_profiles pagination/filtering."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.repositories.agent_repo import AgentRepository


def _mock_db_session(agents=None, count_val=0):
    """Create a mock AsyncSession returning specified agents or count."""
    session = AsyncMock()
    result = MagicMock()
    if agents is not None:
        result.scalars.return_value.all.return_value = agents
    result.scalar_one.return_value = count_val
    session.execute.return_value = result
    return session


class TestListProfilesPagination:
    @pytest.mark.asyncio
    async def test_default_no_limit_no_offset(self):
        db = _mock_db_session(agents=[])
        profiles = await AgentRepository.list_profiles(db)
        assert profiles == []
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_limit_and_offset(self):
        db = _mock_db_session(agents=[])
        await AgentRepository.list_profiles(db, offset=10, limit=5)
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_exclude_ids(self):
        db = _mock_db_session(agents=[])
        await AgentRepository.list_profiles(db, exclude_ids=["id1", "id2"])
        db.execute.assert_called_once()


class TestCountProfiles:
    @pytest.mark.asyncio
    async def test_count_returns_scalar(self):
        db = _mock_db_session(count_val=42)
        count = await AgentRepository.count_profiles(db)
        assert count == 42

    @pytest.mark.asyncio
    async def test_count_with_exclude_ids(self):
        db = _mock_db_session(count_val=10)
        count = await AgentRepository.count_profiles(db, exclude_ids=["hidden1"])
        assert count == 10
        db.execute.assert_called_once()
