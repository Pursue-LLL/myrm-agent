"""Tests for AgentRepository allow_discovery persistence and rehydration.

Covers the previously dead feature path: allow_discovery was written into
AgentProfile metadata but never persisted to the agents table, and never
rehydrated into AgentProfile.metadata, so the team roster filter in
team_protocol.py always saw the default value.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models import Agent
from app.database.repositories.agent_repo import AgentRepository
from myrm_agent_harness.backends.profiles.types import AgentProfile


class TestAgentToProfileRehydration:
    def test_rehydrates_allow_discovery_true(self) -> None:
        agent = Agent(id="a1", name="Agent1", allow_discovery=True)
        profile = AgentRepository._agent_to_profile(agent)
        assert profile.metadata is not None
        assert profile.metadata["allow_discovery"] is True

    def test_rehydrates_allow_discovery_false(self) -> None:
        agent = Agent(id="a1", name="Agent1", allow_discovery=False)
        profile = AgentRepository._agent_to_profile(agent)
        assert profile.metadata is not None
        assert profile.metadata["allow_discovery"] is False


class TestCreateProfilePersistsAllowDiscovery:
    @staticmethod
    def _added_agent(db: AsyncMock) -> Agent:
        for call in db.add.call_args_list:
            obj = call.args[0]
            if isinstance(obj, Agent):
                return obj
        raise AssertionError("Agent was never added to the session")

    @pytest.mark.asyncio
    async def test_create_profile_persists_false(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result
        profile = AgentProfile(
            id="a1",
            display_name="Agent1",
            metadata={"allow_discovery": False},
        )
        await AgentRepository.create_profile(db, profile)
        assert self._added_agent(db).allow_discovery is False

    @pytest.mark.asyncio
    async def test_create_profile_defaults_true_when_missing(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result
        profile = AgentProfile(id="a1", display_name="Agent1", metadata={})
        await AgentRepository.create_profile(db, profile)
        assert self._added_agent(db).allow_discovery is True


class TestUpdateProfileAppliesAllowDiscovery:
    @pytest.mark.asyncio
    async def test_update_profile_turns_discovery_off(self) -> None:
        db = AsyncMock()
        agent = Agent(id="a1", name="Agent1", allow_discovery=True)
        result = MagicMock()
        result.scalar_one_or_none.return_value = agent
        db.execute.return_value = result

        with patch.object(
            AgentRepository, "_agent_to_profile", return_value=MagicMock()
        ):
            await AgentRepository.update_profile(
                db, "a1", {"metadata": {"allow_discovery": False}}
            )

        assert agent.allow_discovery is False
