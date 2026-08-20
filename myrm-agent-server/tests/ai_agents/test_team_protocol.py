"""Tests for team_protocol.py — Leader Operating Protocol generation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_agents.team_protocol import (
    RosterEntry,
    _format_roster,
    _resolve_roster,
    build_leader_protocol_prompt,
)


class TestRosterEntry:
    def test_roster_entry_frozen(self):
        entry = RosterEntry(agent_id="a1", display_name="Agent1", description="Desc")
        assert entry.agent_id == "a1"
        with pytest.raises(AttributeError):
            entry.agent_id = "a2"  # type: ignore[misc]


class TestFormatRoster:
    def test_empty_entries(self):
        result = _format_roster([])
        assert result == "(No team members configured)"

    def test_single_entry(self):
        entries = [RosterEntry("a1", "Writer", "Writes articles")]
        result = _format_roster(entries)
        assert "**Writer**" in result
        assert "`a1`" in result
        assert "Writes articles" in result

    def test_multiple_entries(self):
        entries = [
            RosterEntry("a1", "Writer", "Writes articles"),
            RosterEntry("a2", "Reviewer", "Reviews code"),
        ]
        result = _format_roster(entries)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert "Writer" in lines[0]
        assert "Reviewer" in lines[1]


class TestResolveRoster:
    @pytest.mark.asyncio
    async def test_empty_ids(self):
        result = await _resolve_roster([])
        assert result == []

    @pytest.mark.asyncio
    async def test_resolves_members_concurrently(self):
        mock_profiles = {
            "a1": MagicMock(display_name="Writer", description="Writes"),
            "a2": MagicMock(display_name="Coder", description="Codes"),
        }

        async def mock_get(agent_id: str):
            return mock_profiles.get(agent_id)

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            side_effect=mock_get,
        ):
            result = await _resolve_roster(["a1", "a2"])

        assert len(result) == 2
        assert result[0].display_name == "Writer"
        assert result[1].display_name == "Coder"

    @pytest.mark.asyncio
    async def test_skips_missing_member(self):
        async def mock_get(agent_id: str):
            if agent_id == "a1":
                return MagicMock(display_name="Writer", description="Writes")
            return None

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            side_effect=mock_get,
        ):
            result = await _resolve_roster(["a1", "missing"])

        assert len(result) == 1
        assert result[0].agent_id == "a1"

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        async def mock_get(agent_id: str):
            if agent_id == "a1":
                return MagicMock(display_name="Writer", description="Writes")
            raise RuntimeError("DB error")

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            side_effect=mock_get,
        ):
            result = await _resolve_roster(["a1", "error_agent"])

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_fallback_display_name(self):
        """When display_name is None, use agent_id as fallback."""
        mock_profile = MagicMock(display_name=None, description="Some desc")

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            result = await _resolve_roster(["fallback-id"])

        assert result[0].display_name == "fallback-id"

    @pytest.mark.asyncio
    async def test_fallback_description(self):
        """When description is None, use 'No description' as fallback."""
        mock_profile = MagicMock(display_name="Agent", description=None)

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            result = await _resolve_roster(["id1"])

        assert result[0].description == "No description"


class TestResolveRosterDynamicDiscovery:
    def _profile(self, agent_id: str, *, description: str, metadata: dict | None):
        return MagicMock(
            id=agent_id,
            display_name=f"Agent-{agent_id}",
            description=description,
            metadata=metadata,
        )

    @pytest.mark.asyncio
    async def test_filters_allow_discovery_false(self):
        """Agents with allow_discovery=False must be excluded from the dynamic roster."""
        profiles = [
            self._profile(
                "visible",
                description="Has a description",
                metadata={"allow_discovery": True},
            ),
            self._profile(
                "hidden",
                description="Private agent",
                metadata={"allow_discovery": False},
            ),
        ]

        async def mock_list(page: int, page_size: int):
            return profiles, len(profiles)

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_list",
            new_callable=AsyncMock,
            side_effect=mock_list,
        ):
            result = await _resolve_roster([], dynamic_discovery=True)

        ids = [entry.agent_id for entry in result]
        assert ids == ["visible"]

    @pytest.mark.asyncio
    async def test_defaults_to_true_when_metadata_missing(self):
        """Agents without an allow_discovery key remain discoverable (default behavior)."""
        profiles = [
            self._profile("no-meta", description="Described", metadata=None),
        ]

        async def mock_list(page: int, page_size: int):
            return profiles, len(profiles)

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_list",
            new_callable=AsyncMock,
            side_effect=mock_list,
        ):
            result = await _resolve_roster([], dynamic_discovery=True)

        ids = [entry.agent_id for entry in result]
        assert ids == ["no-meta"]

    @pytest.mark.asyncio
    async def test_excludes_leader_and_descriptionless(self):
        """Leader itself and agents without a description must be skipped."""
        profiles = [
            self._profile(
                "leader",
                description="I am the leader",
                metadata={"allow_discovery": True},
            ),
            self._profile("no-desc", description="", metadata={"allow_discovery": True}),
            self._profile("member", description="A member", metadata={"allow_discovery": True}),
        ]

        async def mock_list(page: int, page_size: int):
            return profiles, len(profiles)

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_list",
            new_callable=AsyncMock,
            side_effect=mock_list,
        ):
            result = await _resolve_roster([], leader_id="leader", dynamic_discovery=True)

        ids = [entry.agent_id for entry in result]
        assert ids == ["member"]

    @pytest.mark.asyncio
    async def test_dynamic_discovery_off_adds_nothing(self):
        """Without dynamic_discovery no agents are scanned."""
        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_list",
            new_callable=AsyncMock,
        ) as mock_list:
            result = await _resolve_roster([], dynamic_discovery=False)

        assert result == []
        mock_list.assert_not_called()

    @pytest.mark.asyncio
    async def test_dynamic_discovery_caps_at_fifteen(self):
        """The dynamic roster must stop after the cap of 15 discoverable agents."""
        profiles = [
            self._profile(
                f"agent-{i}",
                description=f"Description {i}",
                metadata={"allow_discovery": True},
            )
            for i in range(20)
        ]

        async def mock_list(page: int, page_size: int):
            return profiles, len(profiles)

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_list",
            new_callable=AsyncMock,
            side_effect=mock_list,
        ):
            result = await _resolve_roster([], dynamic_discovery=True)

        assert len(result) == 15

    @pytest.mark.asyncio
    async def test_dynamic_discovery_skips_existing_static_members(self):
        """Dynamic candidates already bound as static subagents must not be duplicated."""
        profiles = [
            self._profile("member", description="A member", metadata={"allow_discovery": True}),
            self._profile("extra", description="Extra agent", metadata={"allow_discovery": True}),
        ]

        async def mock_list(page: int, page_size: int):
            return profiles, len(profiles)

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            side_effect=lambda agent_id: MagicMock(display_name=f"Agent-{agent_id}", description=f"Description {agent_id}"),
        ):
            with patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                side_effect=mock_list,
            ):
                result = await _resolve_roster(["member"], dynamic_discovery=True)

        ids = [entry.agent_id for entry in result]
        assert ids == ["member", "extra"]

    @pytest.mark.asyncio
    async def test_dynamic_discovery_handles_list_error(self):
        """A failure while scanning must be swallowed, keeping static members."""
        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            side_effect=lambda agent_id: MagicMock(display_name=f"Agent-{agent_id}", description=f"Description {agent_id}"),
        ):
            with patch(
                "app.services.agent.agent_service.AgentService.get_agent_list",
                new_callable=AsyncMock,
                side_effect=RuntimeError("list failed"),
            ):
                result = await _resolve_roster(["member"], dynamic_discovery=True)

        assert [entry.agent_id for entry in result] == ["member"]


class TestBuildLeaderProtocolPrompt:
    @pytest.mark.asyncio
    async def test_contains_protocol_tags(self):
        mock_profile = MagicMock(display_name="Writer", description="Writes")

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            result = await build_leader_protocol_prompt(["a1"])

        assert "<team_leader_protocol>" in result
        assert "</team_leader_protocol>" in result
        assert "## Role" in result
        assert "## Team Roster" in result
        assert "## Operating Rules" in result
        assert "## Coordination Principles" in result

    @pytest.mark.asyncio
    async def test_includes_roster(self):
        mock_profile = MagicMock(display_name="Writer", description="Writes articles")

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            result = await build_leader_protocol_prompt(["a1"])

        assert "**Writer**" in result
        assert "Writes articles" in result

    @pytest.mark.asyncio
    async def test_empty_subagents(self):
        result = await build_leader_protocol_prompt([])
        assert "(No team members configured)" in result

    @pytest.mark.asyncio
    async def test_all_members_missing(self):
        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await build_leader_protocol_prompt(["x1", "x2"])

        assert "(No team members configured)" in result
