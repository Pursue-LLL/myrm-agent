"""Tests for AgentRepository allow_discovery persistence and rehydration.

Covers default-discoverable semantics (True when absent or None) and
explicit opt-out (False) across create/update/rehydrate paths.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.backends.profiles.types import AgentProfile

from app.database.models import Agent
from app.database.repositories.agent_repo import AgentRepository


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

    def test_rehydrates_none_as_true(self) -> None:
        """Un-persisted/un-flushed rows default to discoverable (not excluded)."""
        agent = Agent(id="a1", name="Agent1", allow_discovery=None)
        profile = AgentRepository._agent_to_profile(agent)
        assert profile.metadata is not None
        assert profile.metadata["allow_discovery"] is True


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

    @pytest.mark.asyncio
    async def test_create_profile_none_defaults_true(self) -> None:
        """Explicit None from a contract must not be coerced to False."""
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result
        profile = AgentProfile(
            id="a1",
            display_name="Agent1",
            metadata={"allow_discovery": None},
        )
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

    @pytest.mark.asyncio
    async def test_update_profile_none_keeps_existing_value(self) -> None:
        """Explicit None must not flip discovery off; it leaves the current value."""
        db = AsyncMock()
        agent = Agent(id="a1", name="Agent1", allow_discovery=True)
        result = MagicMock()
        result.scalar_one_or_none.return_value = agent
        db.execute.return_value = result

        with patch.object(
            AgentRepository, "_agent_to_profile", return_value=MagicMock()
        ):
            await AgentRepository.update_profile(
                db, "a1", {"metadata": {"allow_discovery": None}}
            )

        assert agent.allow_discovery is True
