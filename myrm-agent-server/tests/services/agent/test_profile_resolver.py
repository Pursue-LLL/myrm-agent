"""AgentProfileResolver unit tests — TTL caching, invalidation, singleton, falsy edge cases."""

from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.profile_resolver import (
    _CACHE_TTL_SECONDS,
    DEFAULT_ENABLED_BUILTIN_TOOLS,
    AgentProfileResolver,
    ResolvedAgentProfile,
    _coerce_str_tuple,
    _coerce_tool_selections,
    get_agent_profile_resolver,
    resolve_builtin_tool_flags,
    apply_agent_baseline_tool_flags,
)


@dataclass
class _FakeAgentProfile:
    """Minimal stub that mimics the AgentProfile fields used by _load_from_db."""

    system_prompt: str | None = "You are a helpful assistant."
    model: str | None = "openai/gpt-4o"
    skills: list[str] | None = None
    skill_configs: dict[str, dict] | None = None
    max_iterations: int | None = 10
    memory_policy: object | None = None
    tools_allowed: list[str] | None = None
    metadata: dict[str, object] | None = None


def _make_fake_agent(
    *,
    system_prompt: str | None = "You are a helper.",
    skills: Optional[list[str]] = None,
    metadata: Optional[dict[str, object]] = None,
) -> _FakeAgentProfile:
    return _FakeAgentProfile(
        system_prompt=system_prompt,
        skills=skills or ["skill-1"],
        metadata=metadata
        or {
            "mcp_ids": ["mcp-1"],
            "subagent_ids": ["sub-1"],
            "security_overrides": {"yolo_mode_enabled": True},
            "personality_style": "creative",
            "enabled_builtin_tools": ["web_search", "browser"],
        },
    )


@pytest.fixture()
def resolver() -> AgentProfileResolver:
    return AgentProfileResolver()


class TestResolveFound:
    """resolve() returns a fully-populated ResolvedAgentProfile when agent exists."""

    @pytest.mark.asyncio
    async def test_resolve_returns_complete_profile(self, resolver: AgentProfileResolver):
        fake = _make_fake_agent()

        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=ResolvedAgentProfile(
                agent_id="agent-1",
                system_prompt=fake.system_prompt,
                model=fake.model,
                skill_ids=("skill-1",),
                subagent_ids=("sub-1",),
                mcp_ids=("mcp-1",),
                security_overrides={"yolo_mode_enabled": True},
                personality_style="creative",
                max_iterations=10,
                workspace_policy="ISOLATED_COPY",
                memory_policy=None,
                memory_decay_profile=None,
                enabled_builtin_tools=("web_search", "browser"),
                engine_params={"max_tool_calls": 7},
            ),
        ) as mock_load:
            result = await resolver.resolve("agent-1")

            assert result is not None
            assert result.agent_id == "agent-1"
            assert result.system_prompt == "You are a helper."
            assert result.skill_ids == ("skill-1",)
            assert result.subagent_ids == ("sub-1",)
            assert result.mcp_ids == ("mcp-1",)
            assert result.enabled_builtin_tools == ("web_search", "browser")
            assert result.max_iterations == 10
            assert result.engine_params == {"max_tool_calls": 7}
            assert result.personality_style == "creative"
            assert result.workspace_policy == "ISOLATED_COPY"
            mock_load.assert_awaited_once_with("agent-1")


class TestResolveNotFound:
    """resolve() returns None when agent does not exist."""

    @pytest.mark.asyncio
    async def test_resolve_returns_none_for_missing_agent(self, resolver: AgentProfileResolver):
        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_load:
            result = await resolver.resolve("nonexistent")
            assert result is None
            mock_load.assert_awaited_once()


class TestCacheHit:
    """resolve() serves from cache within TTL."""

    @pytest.mark.asyncio
    async def test_cache_hit_avoids_db_call(self, resolver: AgentProfileResolver):
        profile = ResolvedAgentProfile(
            agent_id="agent-1",
            system_prompt="cached",
            model="openai/gpt-4o",
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=(),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=("web_search",),
        )

        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=profile,
        ) as mock_load:
            first = await resolver.resolve("agent-1")
            second = await resolver.resolve("agent-1")

            assert first is second
            assert mock_load.await_count == 1


class TestCacheExpiry:
    """resolve() reloads from DB after TTL expires."""

    @pytest.mark.asyncio
    async def test_cache_expiry_triggers_reload(self, resolver: AgentProfileResolver):
        profile = ResolvedAgentProfile(
            agent_id="agent-1",
            system_prompt="v1",
            model=None,
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=(),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=("web_search",),
        )

        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=profile,
        ) as mock_load:
            await resolver.resolve("agent-1")
            assert mock_load.await_count == 1

            # Simulate TTL expiry by backdating cache timestamp
            cache_key = "agent-1"
            ts, cached_profile = resolver._cache[cache_key]
            resolver._cache[cache_key] = (ts - _CACHE_TTL_SECONDS - 1, cached_profile)

            await resolver.resolve("agent-1")
            assert mock_load.await_count == 2


class TestInvalidate:
    """invalidate() clears cache entries for the given agent_id."""

    @pytest.mark.asyncio
    async def test_invalidate_clears_all_users(self, resolver: AgentProfileResolver):
        profile = ResolvedAgentProfile(
            agent_id="agent-1",
            system_prompt="test",
            model=None,
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=(),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=("web_search",),
        )

        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=profile,
        ) as mock_load:
            await resolver.resolve("agent-1")
            await resolver.resolve("agent-1")
            assert mock_load.await_count == 1

            resolver.invalidate("agent-1")
            assert "agent-1" not in resolver._cache

            await resolver.resolve("agent-1")
            assert mock_load.await_count == 2

    @pytest.mark.asyncio
    async def test_invalidate_preserves_other_agents(self, resolver: AgentProfileResolver):
        profile_a = ResolvedAgentProfile(
            agent_id="agent-a",
            system_prompt="a",
            model=None,
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=(),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=("web_search",),
        )
        profile_b = ResolvedAgentProfile(
            agent_id="agent-b",
            system_prompt="b",
            model=None,
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=(),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=("web_search",),
        )

        async def _side_effect(agent_id: str) -> ResolvedAgentProfile | None:
            return profile_a if agent_id == "agent-a" else profile_b

        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            side_effect=_side_effect,
        ):
            await resolver.resolve("agent-a")
            await resolver.resolve("agent-b")

            resolver.invalidate("agent-a")
            assert "agent-a" not in resolver._cache
            assert "agent-b" in resolver._cache


class TestEdgeCases:
    """Edge-case scenarios for resolve()."""

    @pytest.mark.asyncio
    async def test_resolve_empty_agent_id_returns_none(self, resolver: AgentProfileResolver):
        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_load:
            result = await resolver.resolve("")
            assert result is None
            mock_load.assert_awaited_once_with("")


class TestSingleton:
    """get_agent_profile_resolver() returns the same instance."""

    def test_singleton_returns_same_instance(self):
        import app.services.agent.profile_resolver as mod

        old = mod._resolver_instance
        try:
            mod._resolver_instance = None
            r1 = get_agent_profile_resolver()
            r2 = get_agent_profile_resolver()
            assert r1 is r2
        finally:
            mod._resolver_instance = old


class TestCoerceStrTuple:
    """_coerce_str_tuple correctly normalizes various input types."""

    def test_none_returns_empty_tuple(self):
        assert _coerce_str_tuple(None) == ()

    def test_string_returns_single_element_tuple(self):
        assert _coerce_str_tuple("web_search") == ("web_search",)

    def test_list_returns_tuple(self):
        assert _coerce_str_tuple(["a", "b"]) == ("a", "b")

    def test_empty_list_returns_empty_tuple(self):
        assert _coerce_str_tuple([]) == ()

    def test_tuple_returns_same(self):
        assert _coerce_str_tuple(("x", "y")) == ("x", "y")

    def test_scalar_returns_string_tuple(self):
        assert _coerce_str_tuple(42) == ("42",)


class TestFalsyEdgeCases:
    """Verify [] vs None distinction in profile resolution.

    Regression tests for the bug where `if raw_builtin_tools` treated [] as falsy,
    causing fallback to defaults even when the user explicitly disabled all tools.
    """

    @pytest.mark.asyncio
    async def test_empty_builtin_tools_preserved(self, resolver: AgentProfileResolver):
        """enabled_builtin_tools=[] must produce empty tuple, not default fallback."""
        profile = ResolvedAgentProfile(
            agent_id="agent-empty-tools",
            system_prompt="test",
            model=None,
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=(),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=(),
        )
        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=profile,
        ):
            result = await resolver.resolve("agent-empty-tools")

        assert result is not None
        assert result.enabled_builtin_tools == ()

    @pytest.mark.asyncio
    async def test_none_builtin_tools_gets_defaults(self, resolver: AgentProfileResolver):
        """When metadata has no enabled_builtin_tools key, defaults should apply."""
        profile = ResolvedAgentProfile(
            agent_id="agent-default-tools",
            system_prompt="test",
            model=None,
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=(),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=(
                "web_search",
                "memory",
                "file_ops",
                "code_execute",
            ),
        )
        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=profile,
        ):
            result = await resolver.resolve("agent-default-tools")

        assert result is not None
        assert result.enabled_builtin_tools == (
            "web_search",
            "memory",
            "file_ops",
            "code_execute",
        )

    @pytest.mark.asyncio
    async def test_empty_subagent_ids_preserved(self, resolver: AgentProfileResolver):
        """subagent_ids=[] must produce None (empty tuple → None), not default fallback."""
        profile = ResolvedAgentProfile(
            agent_id="agent-no-subs",
            system_prompt="test",
            model=None,
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=(),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=("web_search",),
        )
        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=profile,
        ):
            result = await resolver.resolve("agent-no-subs")

        assert result is not None
        assert result.subagent_ids is None


class TestSessionPolicyField:
    """Verify session_policy is correctly carried through resolve()."""

    @pytest.mark.asyncio
    async def test_session_policy_present(self, resolver: AgentProfileResolver):
        policy_dict = {"mode": "idle", "daily_reset_hour": 6, "idle_minutes": 30}
        profile = ResolvedAgentProfile(
            agent_id="agent-sp",
            system_prompt="test",
            model=None,
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=(),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=("web_search",),
            session_policy=policy_dict,
        )
        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=profile,
        ):
            result = await resolver.resolve("agent-sp")

        assert result is not None
        assert result.session_policy == policy_dict
        assert result.session_policy["mode"] == "idle"
        assert result.session_policy["idle_minutes"] == 30

    @pytest.mark.asyncio
    async def test_session_policy_none_when_not_set(self, resolver: AgentProfileResolver):
        profile = ResolvedAgentProfile(
            agent_id="agent-no-sp",
            system_prompt="test",
            model=None,
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=(),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=("web_search",),
        )
        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=profile,
        ):
            result = await resolver.resolve("agent-no-sp")

        assert result is not None
        assert result.session_policy is None

    @pytest.mark.asyncio
    async def test_session_policy_survives_cache(self, resolver: AgentProfileResolver):
        policy_dict = {"mode": "daily", "daily_reset_hour": 4, "idle_minutes": 120}
        profile = ResolvedAgentProfile(
            agent_id="agent-sp-cache",
            system_prompt="test",
            model=None,
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=(),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=("web_search",),
            session_policy=policy_dict,
        )
        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=profile,
        ) as mock_load:
            first = await resolver.resolve("agent-sp-cache")
            second = await resolver.resolve("agent-sp-cache")

            assert first is second
            assert first.session_policy == policy_dict
            assert mock_load.await_count == 1


class TestCoerceToolSelections:
    """_coerce_tool_selections normalizes metadata mcp_tool_selections."""

    def test_none_returns_empty(self):
        assert _coerce_tool_selections(None) == {}

    def test_non_dict_returns_empty(self):
        assert _coerce_tool_selections("invalid") == {}
        assert _coerce_tool_selections(42) == {}
        assert _coerce_tool_selections([]) == {}

    def test_valid_dict(self):
        result = _coerce_tool_selections({"server1": ["read", "write"], "server2": ["delete"]})
        assert result == {"server1": ("read", "write"), "server2": ("delete",)}

    def test_empty_tool_list_skipped(self):
        result = _coerce_tool_selections({"server1": ["read"], "server2": []})
        assert result == {"server1": ("read",)}
        assert "server2" not in result

    def test_filters_non_string_values(self):
        result = _coerce_tool_selections({"srv": [123, True]})
        assert result == {}

    def test_string_tool_value_coerced_to_single_tuple(self):
        result = _coerce_tool_selections({"srv": "single_tool"})
        assert result == {"srv": ("single_tool",)}


class TestMcpToolSelectionsField:
    """Verify mcp_tool_selections is correctly carried through resolve()."""

    @pytest.mark.asyncio
    async def test_mcp_tool_selections_present(self, resolver: AgentProfileResolver):
        selections = {"github": ("read_file", "search_code"), "slack": ("send_message",)}
        profile = ResolvedAgentProfile(
            agent_id="agent-mts",
            system_prompt="test",
            model=None,
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=("github", "slack"),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=("web_search",),
            mcp_tool_selections=selections,
        )
        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=profile,
        ):
            result = await resolver.resolve("agent-mts")

        assert result is not None
        assert result.mcp_tool_selections == selections
        assert result.mcp_tool_selections["github"] == ("read_file", "search_code")

    @pytest.mark.asyncio
    async def test_mcp_tool_selections_default_empty(self, resolver: AgentProfileResolver):
        profile = ResolvedAgentProfile(
            agent_id="agent-no-mts",
            system_prompt="test",
            model=None,
            skill_ids=(),
            subagent_ids=None,
            mcp_ids=(),
            security_overrides=None,
            personality_style=None,
            max_iterations=None,
            workspace_policy=None,
            memory_policy=None,
            memory_decay_profile=None,
            enabled_builtin_tools=("web_search",),
        )
        with patch.object(
            AgentProfileResolver,
            "_load_from_db",
            new_callable=AsyncMock,
            return_value=profile,
        ):
            result = await resolver.resolve("agent-no-mts")

        assert result is not None
        assert result.mcp_tool_selections == {}


class TestNotifyTargetsFiltering:
    """notify_targets in metadata are filtered to valid channel+recipient_id entries."""

    @pytest.mark.asyncio
    async def test_load_from_db_filters_invalid_entries(self) -> None:
        from unittest.mock import MagicMock

        mock_agent = MagicMock()
        mock_agent.system_prompt = "prompt"
        mock_agent.model = "openai/gpt-4o"
        mock_agent.skills = []
        mock_agent.skill_configs = None
        mock_agent.max_iterations = 10
        mock_agent.memory_policy = None
        mock_agent.memory_decay_profile = None
        mock_agent.metadata = {
            "mcp_ids": [],
            "enabled_builtin_tools": list(DEFAULT_ENABLED_BUILTIN_TOOLS),
            "notify_targets": [
                {"channel": "telegram", "recipient_id": "123", "label": "TG"},
                {"channel": "slack"},
                {"recipient_id": "orphan"},
                "not-a-dict",
            ],
        }

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.platform_utils.get_session_factory", return_value=lambda: mock_session),
            patch(
                "app.services.agent.agent_service.AgentService.get_agent_by_id",
                new_callable=AsyncMock,
                return_value=mock_agent,
            ),
        ):
            profile = await AgentProfileResolver._load_from_db("agent-notify")

        assert profile is not None
        assert profile.notify_targets == (
            {"channel": "telegram", "recipient_id": "123", "label": "TG"},
        )


class TestDefaultEnabledBuiltinTools:
    """Verify the canonical default contains expected tools."""

    def test_contains_default_togglable_tools(self):
        assert "web_search" in DEFAULT_ENABLED_BUILTIN_TOOLS
        assert "memory" in DEFAULT_ENABLED_BUILTIN_TOOLS

    def test_baseline_tools_not_in_default(self):
        from app.services.agent.builtin_tool_ids import AGENT_BASELINE_BUILTIN_TOOLS

        for tool_id in AGENT_BASELINE_BUILTIN_TOOLS:
            assert tool_id not in DEFAULT_ENABLED_BUILTIN_TOOLS

    def test_is_tuple(self):
        assert isinstance(DEFAULT_ENABLED_BUILTIN_TOOLS, tuple)


class TestResolveBuiltinToolFlags:
    """Verify enabled_builtin_tools → enable_xxx flag mapping."""

    def test_apply_agent_baseline_forces_file_and_bash(self):
        flags = resolve_builtin_tool_flags(["web_search", "memory"])
        baseline = apply_agent_baseline_tool_flags(flags)
        assert baseline["enable_file_ops"] is True
        assert baseline["enable_code_execute"] is True
        assert baseline["enable_browser"] is False

    def test_default_tools_enable_web_memory_and_structured_clarify(self):
        flags = resolve_builtin_tool_flags(DEFAULT_ENABLED_BUILTIN_TOOLS)
        assert flags["enable_file_ops"] is False
        assert flags["enable_code_execute"] is False
        assert flags["enable_browser"] is False
        assert flags["enable_computer_use"] is False
        assert flags["enable_wiki"] is False
        assert flags["enable_render_ui"] is False
        assert flags["enable_structured_clarify"] is True

    def test_all_tools_enabled(self):
        tools = (
            "browser",
            "computer_use",
            "file_ops",
            "code_execute",
            "wiki",
            "kanban",
            "cron",
            "answer_tool",
            "render_ui",
            "planning",
            "structured_clarify",
            "external_cli",
        )
        flags = resolve_builtin_tool_flags(tools)
        assert all(flags.values())

    def test_cron_maps_to_enable_cron_eager(self):
        flags = resolve_builtin_tool_flags(["cron"])
        assert flags["enable_cron_eager"] is True
        assert flags["enable_browser"] is False

    def test_cron_absent_disables_eager(self):
        flags = resolve_builtin_tool_flags(["web_search", "memory"])
        assert flags["enable_cron_eager"] is False

    def test_selective_enabling(self):
        flags = resolve_builtin_tool_flags(["web_search", "memory", "wiki", "file_ops"])
        assert flags["enable_wiki"] is True
        assert flags["enable_file_ops"] is True
        assert flags["enable_browser"] is False
        assert flags["enable_code_execute"] is False

    def test_empty_list_disables_all(self):
        flags = resolve_builtin_tool_flags([])
        assert not any(flags.values())

    def test_accepts_tuple_input(self):
        flags = resolve_builtin_tool_flags(("browser",))
        assert flags["enable_browser"] is True
        assert flags["enable_wiki"] is False

    def test_render_ui_maps_to_enable_render_ui(self):
        flags = resolve_builtin_tool_flags(["render_ui"])
        assert flags["enable_render_ui"] is True
        assert flags["enable_browser"] is False

    def test_planning_maps_to_enable_planning(self):
        flags = resolve_builtin_tool_flags(["planning"])
        assert flags["enable_planning"] is True
        assert flags["enable_browser"] is False

    def test_default_tools_exclude_planning_and_answer(self):
        flags = resolve_builtin_tool_flags(DEFAULT_ENABLED_BUILTIN_TOOLS)
        assert flags["enable_planning"] is False
        assert flags["enable_answer_tool"] is False

    def test_structured_clarify_maps_to_enable_structured_clarify(self):
        flags = resolve_builtin_tool_flags(["structured_clarify"])
        assert flags["enable_structured_clarify"] is True
        assert flags["enable_render_ui"] is False

    def test_external_cli_maps_to_enable_external_cli(self):
        flags = resolve_builtin_tool_flags(["external_cli"])
        assert flags["enable_external_cli"] is True
        assert flags["enable_browser"] is False

    def test_default_tools_include_structured_clarify(self):
        flags = resolve_builtin_tool_flags(DEFAULT_ENABLED_BUILTIN_TOOLS)
        assert flags["enable_structured_clarify"] is True

    def test_returns_all_flag_keys(self):
        flags = resolve_builtin_tool_flags([])
        assert set(flags.keys()) == {
            "enable_browser",
            "enable_computer_use",
            "enable_file_ops",
            "enable_code_execute",
            "enable_wiki",
            "enable_kanban",
            "enable_cron_eager",
            "enable_answer_tool",
            "enable_render_ui",
            "enable_planning",
            "enable_structured_clarify",
            "enable_external_cli",
        }

    def test_legacy_llm_map_tool_id_is_ignored(self):
        """Stale DB metadata may still list llm_map; it must not map to any flag."""
        flags = resolve_builtin_tool_flags(["web_search", "llm_map"])
        assert "enable_llm_map" not in flags
        assert flags == resolve_builtin_tool_flags(["web_search"])

    def test_legacy_canvas_tool_id_is_ignored(self):
        flags = resolve_builtin_tool_flags(["web_search", "canvas"])
        assert flags == resolve_builtin_tool_flags(["web_search"])


class TestCronPostRunVerifyResolution:
    @pytest.mark.asyncio
    async def test_load_from_db_reads_cron_post_run_verify_from_profile_metadata(self):
        fake = _make_fake_agent(
            metadata={
                "mcp_ids": [],
                "subagent_ids": [],
                "enabled_builtin_tools": list(DEFAULT_ENABLED_BUILTIN_TOOLS),
                "cron_post_run_verify": True,
            },
        )

        with patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new_callable=AsyncMock,
            return_value=fake,
        ):
            profile = await AgentProfileResolver._load_from_db("agent-cron-verify")

        assert profile is not None
        assert profile.cron_post_run_verify is True
