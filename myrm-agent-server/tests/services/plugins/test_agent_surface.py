"""Expert surface of plugin packages: field dispositions and tighten-only projections."""

from __future__ import annotations

import pytest
from myrm_agent_harness.agent.plugins.models import PluginAgent
from myrm_agent_harness.backends.profiles.types import AgentProfile

from app.database.dto import AgentBase
from app.services.plugins.agent_surface import (
    AGENT_FIELD_DISPOSITION,
    IMPORTED_MAX_ITERATIONS_CEILING,
    Disposition,
    filter_tool_selections,
    import_agent_fields,
    profile_to_plugin_agent,
)

# Anything that can widen what an imported expert may do, or that is personal / machine-local.
_NEVER_SHARED = (
    "security_overrides",
    "default_security_preset",
    "trusted_desktop_apps",
    "prompt_mode",
    "workspace_policy",
    "tool_gateway_config",
    "openapi_services",
    "notify_targets",
    "command_bindings",
    "a2a_enabled",
    "a2a_trusted_peer_ids",
    "cron_post_run_verify",
    "home_directory",
    "mounted_skill_ids",
    "skill_configs",
    "memory_policy",
    "auto_restore_domains",
)


class TestFieldDispositionTable:
    def test_every_agent_field_has_a_decision(self) -> None:
        """A new AgentBase field is not shared until someone classifies it (default-deny)."""
        fields = set(AgentBase.model_fields)
        table = set(AGENT_FIELD_DISPOSITION)
        assert fields - table == set(), "unclassified AgentBase fields: add them to agent_surface._FIELD_RULES"
        assert table - fields == set(), "stale entries for fields AgentBase no longer has"

    @pytest.mark.parametrize("field_name", _NEVER_SHARED)
    def test_security_and_machine_local_fields_are_dropped(self, field_name: str) -> None:
        assert AGENT_FIELD_DISPOSITION[field_name] is Disposition.DROP

    def test_model_selection_is_display_only(self) -> None:
        assert AGENT_FIELD_DISPOSITION["model_selection"] is Disposition.DISPLAY

    def test_references_travel_as_names(self) -> None:
        for name in ("skill_ids", "mcp_ids", "subagent_ids"):
            assert AGENT_FIELD_DISPOSITION[name] is Disposition.REFERENCE


class TestImportAgentFields:
    def test_loop_budget_can_only_be_lowered(self) -> None:
        high = import_agent_fields(PluginAgent(name="A", max_iterations=500)).fields["max_iterations"]
        low = import_agent_fields(PluginAgent(name="A", max_iterations=7)).fields["max_iterations"]
        floor = import_agent_fields(PluginAgent(name="A", max_iterations=1)).fields["max_iterations"]
        assert high == IMPORTED_MAX_ITERATIONS_CEILING
        assert low == 7
        assert floor == 5

    def test_missing_loop_budget_stays_unset(self) -> None:
        assert "max_iterations" not in import_agent_fields(PluginAgent(name="A")).fields

    def test_tools_are_limited_to_default_grants_and_the_rest_is_reported(self) -> None:
        imported = import_agent_fields(
            PluginAgent(name="A", tool_names=("web_search", "browser", "shell", "memory", "web_search"))
        )
        assert imported.fields["enabled_builtin_tools"] == ["web_search", "memory"]
        assert imported.withheld_tools == ("browser", "shell")

    def test_all_tools_withheld_falls_back_to_defaults_instead_of_none(self) -> None:
        imported = import_agent_fields(PluginAgent(name="A", tool_names=("browser",)))
        assert "enabled_builtin_tools" not in imported.fields
        assert imported.withheld_tools == ("browser",)

    def test_security_and_unknown_metadata_never_reach_the_fields(self) -> None:
        agent = PluginAgent(
            name="A",
            metadata={
                "security_overrides": {"dangerously_skip_permissions": True},
                "default_security_preset": "explore",
                "trusted_desktop_apps": ["Terminal"],
                "prompt_mode": "naked",
                "workspace_policy": "INHERIT_REQUESTER",
                "required_permissions": ["all"],
                "arbitrary": "value",
            },
        )
        fields = import_agent_fields(agent).fields
        assert set(fields) == {"description", "system_prompt"}

    def test_invalid_optional_values_are_dropped_and_reported(self) -> None:
        agent = PluginAgent(
            name="A",
            metadata={"personality_style": "hacker", "suggestion_prompts": "not-a-list", "allow_discovery": "yes"},
        )
        imported = import_agent_fields(agent)
        assert set(imported.dropped_fields) == {"personality_style", "suggestion_prompts", "allow_discovery"}
        assert set(imported.fields) == {"description", "system_prompt"}

    def test_valid_optional_values_are_carried_and_bounded(self) -> None:
        agent = PluginAgent(
            name="A",
            metadata={
                "personality_style": "friendly",
                "suggestion_prompts": [f"prompt {i} " + "x" * 400 for i in range(10)],
                "allow_discovery": False,
            },
        )
        fields = import_agent_fields(agent).fields
        assert fields["personality_style"] == "friendly"
        assert fields["allow_discovery"] is False
        prompts = fields["suggestion_prompts"]
        assert isinstance(prompts, list) and len(prompts) == 6 and all(len(p) <= 200 for p in prompts)

    def test_name_falls_back_to_slug_and_is_bounded(self) -> None:
        assert import_agent_fields(PluginAgent(name="", metadata={"slug": "lead-bot"})).name == "lead-bot"
        assert len(import_agent_fields(PluginAgent(name="n" * 400)).name) == 255


class TestToolSelections:
    def test_limited_to_resolved_connectors(self) -> None:
        raw = {"fetch": ["get", "post"], "other": ["x"], "empty": []}
        assert filter_tool_selections(raw, {"fetch"}) == {"fetch": ["get", "post"]}

    def test_without_connector_filter_keeps_every_valid_entry(self) -> None:
        assert filter_tool_selections({"a": ["x"], "b": "bad", 3: ["y"]}, None) == {"a": ["x"]}

    def test_non_mapping_is_empty(self) -> None:
        assert filter_tool_selections(["a"], None) == {}


class TestProfileProjection:
    def _profile(self, **overrides: object) -> AgentProfile:
        metadata: dict[str, object] = {
            "personality_style": "concise",
            "suggestion_prompts": ["Summarize this", " "],
            "allow_discovery": False,
            "mcp_tool_selections": {"fetch": ["get"], "gone": ["x"]},
            "security_overrides": {"required_permissions": ["all"]},
            "prompt_mode": "naked",
        }
        profile = AgentProfile(
            id="agent-1",
            display_name="Analyst",
            description="Finds patterns",
            system_prompt="You analyze.",
            max_iterations=30,
            tools_allowed=["web_search", "memory"],
            metadata=metadata,
        )
        for key, value in overrides.items():
            object.__setattr__(profile, key, value)
        return profile

    def test_projects_only_carried_fields(self) -> None:
        agent = profile_to_plugin_agent(
            self._profile(),
            skill_names=("report-writer",),
            mcp_names=("fetch",),
            subagent_names=(),
            is_subagent=False,
            is_entry_agent=True,
        )
        assert agent.name == "Analyst"
        assert agent.system_prompt == "You analyze."
        assert agent.max_iterations == 30
        assert agent.tool_names == ("web_search", "memory")
        assert agent.skill_names == ("report-writer",)
        assert agent.mcp_names == ("fetch",)
        assert agent.is_entry_agent is True
        assert agent.metadata == {
            "personality_style": "concise",
            "suggestion_prompts": ["Summarize this"],
            "allow_discovery": False,
            "mcp_tool_selections": {"fetch": ["get"]},
        }

    def test_default_discovery_is_not_written(self) -> None:
        profile = self._profile()
        profile.metadata = {"allow_discovery": True}
        agent = profile_to_plugin_agent(
            profile, skill_names=(), mcp_names=(), subagent_names=(), is_subagent=False, is_entry_agent=True
        )
        assert agent.metadata == {}
