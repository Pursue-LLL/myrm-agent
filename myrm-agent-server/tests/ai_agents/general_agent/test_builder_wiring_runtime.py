"""What ``build_general_agent`` hands the harness besides tools: skills, MCP servers, workspace, user and guards.

``builder_wiring_testkit`` says what is real and what is stood in for.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.security import CredentialTrack

from app.ai_agents.extensions import SubagentManagementExtension
from app.services.agent.runtime_context import SINGLE_TENANT_USER_ID
from tests.ai_agents.general_agent.builder_wiring_testkit import BUILDER, CHAT_ID, BuilderHarness, mcp_server


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> BuilderHarness:
    return BuilderHarness(monkeypatch)


class TestSkillRuntime:
    async def test_trusted_skills_and_their_environment_reach_the_harness(self, harness: BuilderHarness) -> None:
        harness.skill_cfg.trusted_skill_ids = ["alpha"]
        harness.skill_cfg.skill_env_vars = {"alpha": {"API_URL": "https://api.example"}}
        resolve_env = AsyncMock(return_value={"alpha": {"API_URL": "https://api.example", "TOKEN": "resolved"}})
        harness.patch("app.ai_agents.general_agent.config_builders.resolve_skill_env_map", resolve_env)

        handed = await harness.build(harness.wrapper())

        resolve_env.assert_awaited_once_with(harness.skill_backend, {"alpha": {"API_URL": "https://api.example"}})
        assert handed["trusted_skill_ids"] == ["alpha"]
        assert handed["skill_env_map"] == {"alpha": {"API_URL": "https://api.example", "TOKEN": "resolved"}}

    async def test_without_them_the_harness_is_handed_neither(self, harness: BuilderHarness) -> None:
        handed = await harness.build(harness.wrapper())

        assert handed["trusted_skill_ids"] is None
        assert handed["skill_env_map"] is None

    async def test_the_library_names_come_from_the_skill_backend(self, harness: BuilderHarness) -> None:
        harness.skill_backend.list_skills.return_value = [
            SimpleNamespace(name="alpha", storage_skill_id="id-alpha"),
            SimpleNamespace(name="beta", storage_skill_id=None),
        ]

        handed = await harness.build(harness.wrapper())

        assert handed["library_skill_names"] == frozenset({"alpha", "beta"})

    async def test_an_unreadable_skill_library_costs_the_gap_hints_not_the_agent(
        self, harness: BuilderHarness, caplog: pytest.LogCaptureFixture
    ) -> None:
        harness.skill_backend.list_skills.side_effect = RuntimeError("library offline")

        with caplog.at_level(logging.WARNING, logger=BUILDER):
            handed = await harness.build(harness.wrapper())

        assert handed["library_skill_names"] == frozenset()
        assert "Failed to load skill library names for gap detection (non-blocking): library offline" in caplog.text

    async def test_a_build_without_a_skill_backend_has_no_library_names_and_no_complaint(
        self, harness: BuilderHarness, caplog: pytest.LogCaptureFixture
    ) -> None:
        harness.skill_runtime.skill_backend = None

        with caplog.at_level(logging.WARNING, logger=BUILDER):
            handed = await harness.build(harness.wrapper())

        assert handed["library_skill_names"] == frozenset()
        assert "Failed to load skill library names" not in caplog.text

    async def test_no_skill_backend_means_no_default_instances_and_no_complaint(
        self, harness: BuilderHarness, caplog: pytest.LogCaptureFixture
    ) -> None:
        harness.skill_runtime.skill_backend = None
        harness.patch("app.core.skills.state_manager_instance.get_state_manager", lambda: MagicMock())
        resolve = MagicMock()
        harness.patch("app.services.agent.skill_instance_resolver.resolve_runtime_skill_instance_bindings", resolve)

        with caplog.at_level(logging.WARNING, logger=BUILDER):
            handed = await harness.build(harness.wrapper())

        resolve.assert_not_called()
        assert handed["default_skill_instances"] is None
        assert "Failed to initialize SkillStateManager" not in caplog.text

    async def test_an_agent_without_runtime_skills_resolves_instances_for_an_empty_list(self, harness: BuilderHarness) -> None:
        harness.skill_runtime.runtime_skill_ids = None
        harness.patch("app.core.skills.state_manager_instance.get_state_manager", lambda: MagicMock())
        resolve = MagicMock(return_value={})
        harness.patch("app.services.agent.skill_instance_resolver.resolve_runtime_skill_instance_bindings", resolve)

        await harness.build(harness.wrapper())

        assert resolve.call_args.kwargs["runtime_skill_ids"] == []

    async def test_default_skill_instances_are_resolved_per_skill_name_and_storage_id(self, harness: BuilderHarness) -> None:
        state_manager = MagicMock(name="state_manager")
        harness.patch("app.core.skills.state_manager_instance.get_state_manager", lambda: state_manager)
        harness.skill_backend.list_skills.return_value = [
            SimpleNamespace(name="alpha", storage_skill_id="id-alpha"),
            SimpleNamespace(name="beta", storage_skill_id=None),
        ]
        resolve = MagicMock(return_value={"alpha": "instance-1"})
        harness.patch("app.services.agent.skill_instance_resolver.resolve_runtime_skill_instance_bindings", resolve)
        wrapper = harness.wrapper()

        handed = await harness.build(wrapper)

        resolve.assert_called_once_with(
            runtime_skill_ids=["alpha"],
            skill_configs=wrapper.skill_configs,
            skill_id_to_name={"alpha": "alpha", "id-alpha": "alpha", "beta": "beta"},
            state_manager=state_manager,
        )
        assert handed["state_manager"] is state_manager
        assert handed["default_skill_instances"] == {"alpha": "instance-1"}

    async def test_no_default_instances_means_none_is_handed_over(self, harness: BuilderHarness) -> None:
        harness.patch("app.core.skills.state_manager_instance.get_state_manager", lambda: MagicMock())
        harness.patch(
            "app.services.agent.skill_instance_resolver.resolve_runtime_skill_instance_bindings", MagicMock(return_value={})
        )

        handed = await harness.build(harness.wrapper())

        assert handed["default_skill_instances"] is None

    async def test_a_state_manager_that_cannot_start_costs_the_instances_not_the_agent(
        self, harness: BuilderHarness, caplog: pytest.LogCaptureFixture
    ) -> None:
        def not_initialized() -> object:
            raise RuntimeError("SkillStateManager not initialized")

        harness.patch("app.core.skills.state_manager_instance.get_state_manager", not_initialized)

        with caplog.at_level(logging.WARNING, logger=BUILDER):
            handed = await harness.build(harness.wrapper())

        assert handed["state_manager"] is None
        assert handed["default_skill_instances"] is None
        assert "Failed to initialize SkillStateManager for agent: SkillStateManager not initialized" in caplog.text


class TestMcpServers:
    @pytest.fixture
    def handlers(self, harness: BuilderHarness) -> SimpleNamespace:
        vault, elicitation = MagicMock(name="vault_handler"), MagicMock(name="elicitation_handler")
        build_vault, build_elicitation = MagicMock(return_value=vault), MagicMock(return_value=elicitation)
        harness.patch("app.ai_agents.general_agent.mcp_vault_handler.build_mcp_vault_handler", build_vault)
        harness.patch("app.services.agent.backends.mcp_elicitation_handler.build_mcp_elicitation_handler", build_elicitation)
        return SimpleNamespace(vault=vault, elicitation=elicitation, build_vault=build_vault, build_elicitation=build_elicitation)

    async def test_each_server_is_prepared_for_the_agent_then_given_its_result_and_elicitation_handlers(
        self, harness: BuilderHarness, handlers: SimpleNamespace
    ) -> None:
        configured = [mcp_server("files"), mcp_server("search")]
        prepared = [mcp_server("files"), mcp_server("search")]
        prepare = AsyncMock(return_value=prepared)
        harness.patch("app.services.agent.mcp_runtime_prepare.prepare_mcp_configs_for_runtime", prepare)
        wrapper = harness.wrapper(agent_id="agent-1", mcp_cfg=configured, declared_allowed_roots=("/work/space",))

        handed = await harness.build(wrapper)

        prepare.assert_awaited_once_with("agent-1", configured)
        handlers.build_vault.assert_called_once_with("/work/space")
        handlers.build_elicitation.assert_called_once_with(agent_id="agent-1", chat_id=CHAT_ID)
        servers = handed["spec"].mcp_servers
        assert [server.name for server in servers] == ["files", "search"]
        assert all(server.oversized_result_handler is handlers.vault for server in servers)
        assert all(server.elicitation_handler is handlers.elicitation for server in servers)

    async def test_without_a_workspace_the_servers_get_no_result_handler(
        self, harness: BuilderHarness, handlers: SimpleNamespace
    ) -> None:
        prepare = AsyncMock()
        harness.patch("app.services.agent.mcp_runtime_prepare.prepare_mcp_configs_for_runtime", prepare)

        handed = await harness.build(harness.wrapper(mcp_cfg=[mcp_server("files")]))

        prepare.assert_not_awaited()  # no agent to prepare them for
        handlers.build_vault.assert_not_called()
        handlers.build_elicitation.assert_called_once_with(agent_id="default", chat_id=CHAT_ID)
        (server,) = handed["spec"].mcp_servers
        assert server.oversized_result_handler is None
        assert server.elicitation_handler is handlers.elicitation

    async def test_a_server_set_that_cannot_be_prepared_is_used_as_configured(
        self, harness: BuilderHarness, handlers: SimpleNamespace, caplog: pytest.LogCaptureFixture
    ) -> None:
        harness.patch(
            "app.services.agent.mcp_runtime_prepare.prepare_mcp_configs_for_runtime",
            AsyncMock(side_effect=RuntimeError("vault locked")),
        )

        with caplog.at_level(logging.WARNING, logger=BUILDER):
            handed = await harness.build(harness.wrapper(agent_id="agent-1", mcp_cfg=[mcp_server("files")]))

        assert [server.name for server in handed["spec"].mcp_servers] == ["files"]
        assert "Failed to prepare MCP configs for agent agent-1: vault locked" in caplog.text

    async def test_an_agent_without_servers_builds_none_of_it(self, harness: BuilderHarness, handlers: SimpleNamespace) -> None:
        prepare = AsyncMock()
        harness.patch("app.services.agent.mcp_runtime_prepare.prepare_mcp_configs_for_runtime", prepare)

        handed = await harness.build(harness.wrapper(agent_id="agent-1"))

        prepare.assert_not_awaited()
        handlers.build_vault.assert_not_called()
        handlers.build_elicitation.assert_not_called()
        assert handed["spec"].mcp_servers == []


class TestWorkspace:
    async def test_the_first_allowed_root_becomes_the_agents_workspace(self, harness: BuilderHarness) -> None:
        handed = await harness.build(harness.wrapper(declared_allowed_roots=("/work/space", "/other")))

        binding = handed["spec"].workspace_binding
        assert (binding.mode, binding.root_path, binding.chat_id) == ("chat", "/work/space", CHAT_ID)
        assert handed["task_workspace_root"] == "/work/space"

    async def test_an_agent_without_allowed_roots_has_no_workspace(self, harness: BuilderHarness) -> None:
        handed = await harness.build(harness.wrapper())

        assert handed["spec"].workspace_binding is None
        assert handed["task_workspace_root"] is None


class TestHandOff:
    @pytest.mark.parametrize(("user_id", "expected"), [(None, SINGLE_TENANT_USER_ID), ("user-7", "user-7")])
    async def test_the_agent_runs_for_the_given_user_or_the_single_tenant_owner(
        self, harness: BuilderHarness, user_id: str | None, expected: str
    ) -> None:
        wrapper = harness.wrapper()

        await harness.build(wrapper, user_id=user_id)

        assert wrapper._task_user_id == expected  # noqa: SLF001

    async def test_the_subagent_extension_carries_the_turns_credential_track_and_precedes_the_security_extension(
        self, harness: BuilderHarness
    ) -> None:
        wrapper = harness.wrapper(subagent_ids=["explore"], credential_track=CredentialTrack.SHARED, incognito_mode=True)

        await harness.build(wrapper)

        registered = [call.args[0] for call in harness.agent.register_extension.call_args_list]
        subagents = [ext for ext in registered if isinstance(ext, SubagentManagementExtension)]
        assert len(subagents) == 1
        assert (subagents[0].credential_track, subagents[0].subagent_ids, subagents[0].incognito_mode) == (
            CredentialTrack.SHARED,
            ["explore"],
            True,
        )
        assert registered.index(subagents[0]) == len(registered) - 2

    async def test_a_deployment_without_subagent_delegation_registers_no_subagent_extension(
        self, harness: BuilderHarness, caplog: pytest.LogCaptureFixture
    ) -> None:
        harness.patch(f"{BUILDER}._should_enable_subagent_tools", lambda: False)

        with caplog.at_level(logging.WARNING, logger=BUILDER):
            await harness.build(harness.wrapper(subagent_ids=["explore"]))

        registered = [call.args[0] for call in harness.agent.register_extension.call_args_list]
        assert not any(isinstance(ext, SubagentManagementExtension) for ext in registered)
        assert len(registered) == 4
        assert "Subagent tools are NOT enabled. Skipping SubagentManagementExtension." in caplog.text


class TestBudgetGuard:
    async def test_the_process_budget_guard_is_attached_to_the_agent(self, harness: BuilderHarness) -> None:
        guard = MagicMock(name="budget_guard")
        harness.patch("app.services.budget.enforcer.get_budget_guard", AsyncMock(return_value=guard))

        await harness.build(harness.wrapper())

        assert harness.agent.budget_checker is guard

    async def test_without_a_guard_the_agent_is_left_unchecked(self, harness: BuilderHarness) -> None:
        await harness.build(harness.wrapper())

        assert harness.agent.budget_checker is None

    async def test_a_guard_that_cannot_load_costs_the_budget_check_not_the_agent(
        self, harness: BuilderHarness, caplog: pytest.LogCaptureFixture
    ) -> None:
        harness.patch("app.services.budget.enforcer.get_budget_guard", AsyncMock(side_effect=RuntimeError("policy store down")))

        with caplog.at_level(logging.WARNING, logger=BUILDER):
            await harness.build(harness.wrapper())

        assert harness.agent.budget_checker is None
        assert "Failed to load budget guard (non-blocking): policy store down" in caplog.text
