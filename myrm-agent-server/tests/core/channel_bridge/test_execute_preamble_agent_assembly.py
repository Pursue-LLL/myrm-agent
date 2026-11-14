"""The agent a channel turn builds: its model and fallbacks, its MCP servers, the images it can read, and how it fails.

An agent profile may pick its own model and MCP servers; the user's providers supply the fallback chains and the vision
model that reads the images a text-only model cannot. A failure to build the agent must not touch an approval another
turn has answered.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.channels.i18n import get_text
from app.channels.routing.pending_approvals import METADATA_APPROVAL_TIMED_OUT_KEY
from app.channels.types import ProgressUpdate
from app.core.channel_bridge.config_loader import UserConfigs
from app.core.types.business import MCPServerConfig, ModelConfig
from app.services.agent.profile.profile_resolver import ResolvedAgentProfile

from .preamble_testkit import build_agent, captured_agent_params, inbound_message, minimal_user_configs

_AGENT = "app.core.channel_bridge.agent_executor.execute_preamble.agent"
_APPROVAL_KEY = "telegram:chat-1"


def _profile(**overrides: object) -> ResolvedAgentProfile:
    fields: dict[str, object] = {
        "agent_id": "agent-1",
        "skill_ids": (),
        "mcp_ids": (),
        "enabled_builtin_tools": ("code_execution",),
        **overrides,
    }
    return ResolvedAgentProfile(**fields)


def _configs(**overrides: object) -> UserConfigs:
    return replace(minimal_user_configs(), **overrides)


def _model(name: str, **overrides: object) -> ModelConfig:
    return ModelConfig(model=name, api_key=f"{name}-key", **overrides)


def _server(name: str) -> MCPServerConfig:
    return MCPServerConfig(name=name, type="sse", url=f"https://{name}.example/sse")


class TestSharedMemoryContexts:
    async def test_the_contexts_the_chat_shares_reach_the_agent(self) -> None:
        with (
            captured_agent_params() as captured,
            patch(
                "app.services.memory.shared_context.shared_context.resolve_shared_context_ids",
                new_callable=AsyncMock,
                return_value=["customer-a"],
            ),
        ):
            await build_agent(inbound_message())

        assert captured["params"].memory_shared_context_ids == ["customer-a"]

    async def test_a_store_that_cannot_be_read_costs_the_turn_its_shared_contexts_not_the_turn(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            captured_agent_params() as captured,
            patch(
                "app.services.memory.shared_context.shared_context.resolve_shared_context_ids",
                new_callable=AsyncMock,
                side_effect=RuntimeError("store down"),
            ),
            caplog.at_level(logging.WARNING, logger=_AGENT),
        ):
            outcome = await build_agent(inbound_message())

        assert outcome.result is not None
        assert captured["params"].memory_shared_context_ids == []
        assert "Failed to resolve shared memory contexts for channel message: store down" in caplog.text


class TestAgentModel:
    async def test_a_profile_that_names_a_model_runs_on_it_with_its_true_context_window(self) -> None:
        providers: dict[str, object] = {"providers": []}
        chosen = _model("profile-model")
        enriched = chosen.model_copy(update={"max_context_tokens": 64_000})

        with (
            captured_agent_params() as captured,
            patch("app.core.channel_bridge.model_resolver.resolve_model_config", return_value=chosen) as resolve,
            patch("app.core.channel_bridge.model_resolver.enrich_model_context_window", return_value=enriched) as enrich,
        ):
            await build_agent(
                inbound_message(),
                configs=_configs(providers_dict=providers),
                resolved_profile=_profile(model="openai/profile-model"),
            )

        resolve.assert_called_once_with(providers, model_override="openai/profile-model")
        enrich.assert_called_once_with(chosen, providers)
        assert captured["params"].model_cfg is enriched

    @pytest.mark.parametrize("profile", [None, _profile()], ids=["no-profile", "profile-without-model"])
    async def test_otherwise_the_agent_runs_on_the_users_default_model(self, profile: ResolvedAgentProfile | None) -> None:
        configs = minimal_user_configs()

        with (
            captured_agent_params() as captured,
            patch("app.core.channel_bridge.model_resolver.resolve_model_config") as resolve,
        ):
            await build_agent(inbound_message(), configs=configs, resolved_profile=profile)

        resolve.assert_not_called()
        assert captured["params"].model_cfg is configs.model_cfg


class TestFallbackChains:
    async def test_the_head_of_each_chain_backs_up_the_model_when_the_caller_names_none(self) -> None:
        configs = _configs(providers_dict={"providers": []})
        main_chain = [_model("backup-main"), _model("backup-main-2")]
        lite_chain = [_model("backup-lite"), _model("backup-lite-2")]

        with (
            captured_agent_params() as captured,
            patch(
                "app.core.channel_bridge.config_parsers.resolve_chat_fallback_chains_from_providers",
                return_value=(main_chain, lite_chain),
            ) as chains,
        ):
            await build_agent(inbound_message(), configs=configs)

        chains.assert_called_once_with(configs.providers_dict, require_tool_calling=True)
        params = captured["params"]
        assert params.fallback_model_cfg is main_chain[0]
        assert params.fallback_lite_model_cfg is lite_chain[0]
        assert params.fallback_model_cfgs == main_chain
        assert params.fallback_lite_model_cfgs == lite_chain

    async def test_a_fallback_the_caller_names_is_never_replaced_by_the_chain(self) -> None:
        named_main, named_lite = _model("named-main"), _model("named-lite")

        with (
            captured_agent_params() as captured,
            patch(
                "app.core.channel_bridge.config_parsers.resolve_chat_fallback_chains_from_providers",
                return_value=([_model("chain-main")], [_model("chain-lite")]),
            ),
        ):
            await build_agent(
                inbound_message(),
                configs=_configs(providers_dict={"providers": []}),
                fallback_model_cfg=named_main,
                fallback_lite_model_cfg=named_lite,
            )

        assert captured["params"].fallback_model_cfg is named_main
        assert captured["params"].fallback_lite_model_cfg is named_lite

    async def test_without_providers_the_agent_has_no_fallback_at_all(self) -> None:
        with captured_agent_params() as captured:
            await build_agent(inbound_message())

        params = captured["params"]
        assert params.fallback_model_cfg is None
        assert params.fallback_lite_model_cfg is None
        assert params.fallback_model_cfgs is None
        assert params.fallback_lite_model_cfgs is None


class TestInboundImages:
    _IMAGE_QUERY: list[dict[str, object]] = [
        {"type": "text", "text": "What is this?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
    ]

    @pytest.fixture
    def analysis(self) -> Iterator[AsyncMock]:
        with patch(
            "app.core.utils.chat_utils.preprocess_inbound_multimodal_query",
            new_callable=AsyncMock,
            return_value="[image: a cat] What is this?",
        ) as preprocess:
            yield preprocess

    async def test_a_text_only_model_gets_the_images_described_by_the_vision_model(self, analysis: AsyncMock) -> None:
        msg = inbound_message()
        configs = minimal_user_configs()
        vision = _model("vision-model", supports_vision=True)

        with captured_agent_params() as captured:
            outcome = await build_agent(msg, configs=configs, query=self._IMAGE_QUERY, vision_fallback_model_cfg=vision)

        assert outcome.result is not None
        analysis.assert_awaited_once_with(
            self._IMAGE_QUERY,
            model_cfg=configs.model_cfg,
            vision_fallback_model_cfg=vision,
            vision_fallback_model_cfgs=[vision],
            meta={"message_id": msg.message_id, "chat_id": "chat-db-id"},
        )
        assert captured["params"].query == "[image: a cat] What is this?"
        assert outcome.result.query_input == "[image: a cat] What is this?"
        assert outcome.pre_events == (ProgressUpdate(label=get_text(msg, "analyzing_image")),)

    async def test_a_model_that_sees_images_receives_them_as_sent(self, analysis: AsyncMock) -> None:
        configs = _configs(model_cfg=_model("seeing-model", supports_vision=True))

        with captured_agent_params() as captured:
            outcome = await build_agent(
                inbound_message(),
                configs=configs,
                query=self._IMAGE_QUERY,
                vision_fallback_model_cfg=_model("vision-model", supports_vision=True),
            )

        analysis.assert_not_awaited()
        assert captured["params"].query == self._IMAGE_QUERY
        assert outcome.pre_events == ()

    async def test_a_text_only_model_without_a_vision_model_gets_the_images_as_sent(self, analysis: AsyncMock) -> None:
        with captured_agent_params() as captured:
            outcome = await build_agent(inbound_message(), query=self._IMAGE_QUERY)

        analysis.assert_not_awaited()
        assert captured["params"].query == self._IMAGE_QUERY
        assert outcome.pre_events == ()

    async def test_a_message_without_attachments_never_runs_the_image_analysis(self, analysis: AsyncMock) -> None:
        with captured_agent_params():
            outcome = await build_agent(
                inbound_message(),
                query="just words",
                vision_fallback_model_cfg=_model("vision-model", supports_vision=True),
            )

        analysis.assert_not_awaited()
        assert outcome.pre_events == ()

    async def test_a_resumed_turn_never_runs_the_image_analysis(self, analysis: AsyncMock) -> None:
        msg = inbound_message(resume_value={"decision": "reject", "timed_out": True})
        msg.metadata[METADATA_APPROVAL_TIMED_OUT_KEY] = True

        with captured_agent_params():
            outcome = await build_agent(
                msg,
                is_resume=True,
                query=self._IMAGE_QUERY,
                vision_fallback_model_cfg=_model("vision-model", supports_vision=True),
            )

        analysis.assert_not_awaited()
        assert outcome.pre_events == ()


class TestMcpSelection:
    _SERVERS = [_server("files"), _server("search"), _server("db")]

    async def test_a_profile_keeps_only_its_servers_and_narrows_them_to_its_tools(self) -> None:
        profile = _profile(mcp_ids=("files", "search"), mcp_tool_selections={"files": ("read_file",)})

        with captured_agent_params() as captured:
            await build_agent(inbound_message(), mcp_configs=self._SERVERS, resolved_profile=profile)

        files, search = captured["params"].mcp_cfg
        assert (files.name, files.tool_include) == ("files", ["read_file"])
        assert (search.name, search.tool_include) == ("search", None)

    async def test_a_profile_that_constrains_nothing_leaves_every_server_as_configured(self) -> None:
        with captured_agent_params() as captured:
            await build_agent(inbound_message(), mcp_configs=self._SERVERS, resolved_profile=_profile())

        assert captured["params"].mcp_cfg == self._SERVERS

    async def test_without_a_profile_every_configured_server_is_mounted(self) -> None:
        with captured_agent_params() as captured:
            await build_agent(inbound_message(), mcp_configs=self._SERVERS)

        assert captured["params"].mcp_cfg == self._SERVERS

    async def test_a_profile_whose_servers_are_all_gone_mounts_none(self) -> None:
        with captured_agent_params() as captured:
            await build_agent(
                inbound_message(),
                mcp_configs=self._SERVERS,
                resolved_profile=_profile(mcp_ids=("removed",)),
            )

        assert captured["params"].mcp_cfg is None


class TestAssemblyFailure:
    async def test_a_live_turn_that_cannot_build_its_agent_leaves_another_turns_approval_answer_alone(self) -> None:
        scheduler = ApprovalTimeoutScheduler.get()
        scheduler.reopen(_APPROVAL_KEY)
        assert scheduler.resolve_if_first(_APPROVAL_KEY) is True  # another turn's answer holds the claim

        try:
            with (
                captured_agent_params(),
                patch(f"{_AGENT}.AgentFactory.create_general_agent", side_effect=RuntimeError("assembly failed")),
                pytest.raises(RuntimeError, match="assembly failed"),
            ):
                await build_agent(inbound_message())

            assert scheduler.resolve_if_first(_APPROVAL_KEY) is False
        finally:
            scheduler.reopen(_APPROVAL_KEY)
