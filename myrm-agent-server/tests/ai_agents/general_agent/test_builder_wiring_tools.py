"""What ``build_general_agent`` mounts for the flags an agent carries: tools, memory, external agents and goals.

``builder_wiring_testkit`` says what is real and what is stood in for.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai_agents.general_agent.mount_resolver import ResolvedMountPlan
from app.core.skills.creation.version_persisting_backend import VersionPersistingSkillWriteBackend
from app.core.skills.marketplace.market_service import market_service
from tests.ai_agents.general_agent.builder_wiring_testkit import (
    BASE_TOOLS,
    BUILDER,
    CHAT_ID,
    BuilderHarness,
    allowed_tools,
)


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> BuilderHarness:
    return BuilderHarness(monkeypatch)


class TestToolMounts:
    async def test_a_plain_agent_mounts_only_the_base_tools(self, harness: BuilderHarness) -> None:
        handed = await harness.build(harness.wrapper())

        assert harness.mounted() == BASE_TOOLS
        assert allowed_tools(handed) == BASE_TOOLS

    async def test_a_tool_without_a_name_is_never_offered_to_the_model(self, harness: BuilderHarness) -> None:
        wrapper = harness.wrapper()
        recorded = wrapper._setup_clarification_tools  # noqa: SLF001

        def clarification_with_a_nameless_tool(tools: list[object]) -> None:
            recorded(tools)
            tools.append(SimpleNamespace(name=None))
            tools.append(object())

        harness.monkeypatch.setattr(wrapper, "_setup_clarification_tools", clarification_with_a_nameless_tool)

        handed = await harness.build(wrapper)

        assert allowed_tools(handed) == BASE_TOOLS
        assert len(handed["tools"]) == len(BASE_TOOLS) + 2

    @pytest.mark.parametrize(("deployment_allows", "mounted"), [(True, True), (False, False)])
    async def test_eager_cron_tools_follow_the_deployment_entitlement(
        self, harness: BuilderHarness, deployment_allows: bool, mounted: bool
    ) -> None:
        harness.patch(f"{BUILDER}._should_enable_cron_tools", lambda: deployment_allows)

        await harness.build(harness.wrapper(enable_cron_eager=True))

        assert bool(harness.calls["cron"]) is mounted

    async def test_cron_tools_stay_lazy_unless_the_agent_asks_for_them_eagerly(self, harness: BuilderHarness) -> None:
        await harness.build(harness.wrapper(enable_cron_eager=False))

        assert harness.calls["cron"] == []

    @pytest.mark.parametrize(
        ("browser", "computer_use"),
        [(True, True), (True, False), (False, True), (False, False)],
        ids=["both", "browser-only", "desktop-only", "neither"],
    )
    async def test_browser_and_desktop_tools_are_mounted_exactly_as_the_mount_plan_says(
        self, harness: BuilderHarness, browser: bool, computer_use: bool
    ) -> None:
        harness.patch(
            "app.ai_agents.general_agent.mount_resolver.resolve_agent_mount",
            lambda **_: ResolvedMountPlan(mount_browser=browser, mount_computer_use=computer_use, mount_widget_capability=False),
        )

        handed = await harness.build(harness.wrapper(enable_browser=True, enable_computer_use=True))

        assert [name for name in ("browser", "computer_use") if name in allowed_tools(handed)] == [
            name for name, mounted in (("browser", browser), ("computer_use", computer_use)) if mounted
        ]
        assert len(harness.calls["browser"]) == int(browser)
        assert len(harness.calls["computer_use"]) == int(computer_use)

    async def test_the_browser_is_set_up_for_the_chat_with_the_agents_vision_model_and_memory(
        self, harness: BuilderHarness
    ) -> None:
        harness.patch(
            "app.ai_agents.general_agent.mount_resolver.resolve_agent_mount",
            lambda **_: ResolvedMountPlan(mount_browser=True, mount_computer_use=False, mount_widget_capability=False),
        )

        await harness.build(harness.wrapper())

        ((args, kwargs),) = harness.calls["browser"]
        assert args[1:] == (CHAT_ID,)
        assert kwargs == {"vision_llm": harness.llm, "memory_manager": None}

    async def test_a_kanban_agent_gets_the_kanban_tools(self, harness: BuilderHarness) -> None:
        kanban = AsyncMock()
        harness.patch(f"{BUILDER}._setup_kanban_tools", kanban)
        kanban_wrapper = harness.wrapper(enable_kanban=True)

        await harness.build(kanban_wrapper)

        kanban.assert_awaited_once()
        assert kanban.await_args.args[0] is kanban_wrapper

    async def test_any_other_agent_gets_no_kanban_tools(self, harness: BuilderHarness) -> None:
        kanban = AsyncMock()
        harness.patch(f"{BUILDER}._setup_kanban_tools", kanban)

        await harness.build(harness.wrapper(enable_kanban=False))

        kanban.assert_not_awaited()

    async def test_the_skill_market_is_mounted_with_the_market_service_when_enabled(self, harness: BuilderHarness) -> None:
        await harness.build(harness.wrapper(enable_skill_market=True))

        ((args, _),) = harness.calls["skill_market"]
        assert args[1] is market_service

    @pytest.mark.parametrize("flag", ["enable_skill_manage", "force_skill_manage"])
    async def test_skill_management_is_mounted_with_a_versioning_write_backend(self, harness: BuilderHarness, flag: str) -> None:
        await harness.build(harness.wrapper(**{flag: True}))

        ((args, kwargs),) = harness.calls["skill_manage"]
        assert isinstance(args[1], VersionPersistingSkillWriteBackend)
        assert args[2] is harness.skill_backend
        assert kwargs == {"auxiliary_llm": harness.llm}

    async def test_skill_management_audits_with_the_fallback_model_when_there_is_one(self, harness: BuilderHarness) -> None:
        harness.llm_bundle.fallback_llm = MagicMock(name="fallback_llm")

        await harness.build(harness.wrapper(enable_skill_manage=True))

        ((_, kwargs),) = harness.calls["skill_manage"]
        assert kwargs["auxiliary_llm"] is harness.llm_bundle.fallback_llm

    async def test_neither_skill_tool_is_mounted_unless_asked_for(self, harness: BuilderHarness) -> None:
        await harness.build(harness.wrapper())

        assert harness.calls["skill_market"] == harness.calls["skill_manage"] == []


class TestMemory:
    async def test_a_memory_enabled_agent_gets_its_memory_tools_and_manager(self, harness: BuilderHarness) -> None:
        manager = MagicMock(name="memory_manager")
        create_memory = AsyncMock(return_value=manager)
        wrapper = harness.wrapper(enable_memory=True)
        harness.monkeypatch.setattr(wrapper, "_create_memory_tools", create_memory)

        handed = await harness.build(wrapper)

        create_memory.assert_awaited_once()
        assert handed["memory_manager"] is manager
        assert harness.build_sandbox.await_args.kwargs["memory_manager"] is manager

    @pytest.mark.parametrize("params", [{"enable_memory": False}, {"enable_memory": True, "incognito_mode": True}])
    async def test_an_agent_that_must_not_remember_gets_no_memory_manager(
        self, harness: BuilderHarness, params: dict[str, bool]
    ) -> None:
        create_memory = AsyncMock()
        wrapper = harness.wrapper(**params)
        harness.monkeypatch.setattr(wrapper, "_create_memory_tools", create_memory)

        handed = await harness.build(wrapper)

        create_memory.assert_not_awaited()
        assert handed["memory_manager"] is None


class TestExternalAgents:
    async def test_an_agent_with_external_cli_gets_the_runtime_pool_and_the_delegate_tool(self, harness: BuilderHarness) -> None:
        wrapper = harness.wrapper(enable_external_cli=True, declared_allowed_roots=("/work/space",))

        await harness.build(wrapper)

        ((_, kwargs),) = harness.calls["external_agents"]
        assert kwargs == {"mount_invoke_acp_agent_tool": True, "external_agent_workdir": "/work/space"}
        assert wrapper._runtime_pool_scope_id == CHAT_ID  # noqa: SLF001

    async def test_a_forced_external_agent_gets_the_pool_without_the_redundant_delegate_tool(
        self, harness: BuilderHarness
    ) -> None:
        await harness.build(harness.wrapper(force_external_agent="claude-code"))

        ((_, kwargs),) = harness.calls["external_agents"]
        assert kwargs == {"mount_invoke_acp_agent_tool": False, "external_agent_workdir": None}

    async def test_an_agent_without_external_cli_gets_no_pool(self, harness: BuilderHarness) -> None:
        wrapper = harness.wrapper()

        await harness.build(wrapper)

        assert harness.calls["external_agents"] == []
        assert wrapper._runtime_pool_scope_id == CHAT_ID  # noqa: SLF001


class TestGoals:
    def _provider(self, harness: BuilderHarness, *, active_goal: object) -> tuple[MagicMock, MagicMock]:
        """The chat's goal provider and the harness factory of the goal tools it is handed to."""
        provider = MagicMock(name="goal_provider")
        provider.get_active_goal = AsyncMock(return_value=active_goal)
        create_tools = MagicMock(return_value=[SimpleNamespace(name="complete_goal_tool")])
        harness.patch("app.services.agent.goals.goal_registry.GoalRegistry.get_provider", lambda _chat_id: provider)
        harness.patch("myrm_agent_harness.agent.meta_tools.goals.goal_agent_tools.create_goal_tools", create_tools)
        return provider, create_tools

    async def test_an_active_goal_turns_planning_on_and_mounts_the_goal_tools(self, harness: BuilderHarness) -> None:
        provider, create_tools = self._provider(harness, active_goal=SimpleNamespace(id="goal-1"))

        handed = await harness.build(harness.wrapper(enable_planning=False))

        provider.get_active_goal.assert_awaited_once_with(CHAT_ID)
        create_tools.assert_called_once_with(provider, CHAT_ID)
        assert handed["enable_planning"] is True
        assert "complete_goal_tool" in allowed_tools(handed)

    async def test_a_provider_with_no_active_goal_changes_nothing(self, harness: BuilderHarness) -> None:
        _, create_tools = self._provider(harness, active_goal=None)

        handed = await harness.build(harness.wrapper(enable_planning=False))

        create_tools.assert_not_called()
        assert handed["enable_planning"] is False
        assert "complete_goal_tool" not in allowed_tools(handed)

    async def test_without_a_goal_provider_the_agents_own_planning_choice_stands(self, harness: BuilderHarness) -> None:
        harness.patch("app.services.agent.goals.goal_registry.GoalRegistry.get_provider", lambda _chat_id: None)

        handed = await harness.build(harness.wrapper(enable_planning=True))

        assert handed["enable_planning"] is True
