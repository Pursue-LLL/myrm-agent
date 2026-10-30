"""Shared builders for the preamble tests.

An inbound message, user configs, ``build_channel_execution_agent`` with every argument but the varying ones at its plain
default, and the turn it assembles for a message.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.ai_agents.agents import GeneralAgentParams
from app.channels.routing.identity_scope import TurnMemoryScope
from app.channels.types import InboundMessage
from app.core.channel_bridge.agent_executor.execute_preamble.agent import build_channel_execution_agent
from app.core.channel_bridge.agent_executor.execute_preamble.types import ChannelAgentBuildOutcome, ChannelAgentBuildResult
from app.core.channel_bridge.config_loader import UserConfigs
from app.core.types.business import ModelConfig

OWNER_MEMORY_SCOPE = TurnMemoryScope(policy=None, extra_namespaces=(), is_compartment=False)


def inbound_message(*, resume_value: dict[str, object] | None = None, locale: str = "en") -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="Hello",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="chat-1",
        user_id="user-1",
        is_group=False,
        mentioned=False,
        metadata={"locale": locale},
        resume_value=resume_value,
    )


def minimal_user_configs(*, search_configured: bool = False) -> UserConfigs:
    return UserConfigs(
        model_cfg=ModelConfig(model="test-model", api_key="test-key"),
        search_cfg=SearchServiceConfig(search_service="searxng", api_base="http://127.0.0.1:8080") if search_configured else None,
        search_is_user_configured=search_configured,
        retrieval_dict=None,
        personal_settings_dict={},
        mcp_dict=None,
        providers_dict=None,
    )


async def build_agent(
    msg: InboundMessage,
    *,
    is_resume: bool = False,
    configs: UserConfigs | None = None,
    enabled_builtin_tools: list[str] | None = None,
    query: str | list[dict[str, object]] = "test query",
    memory_settings: dict[str, object] | None = None,
    memory_scope: TurnMemoryScope = OWNER_MEMORY_SCOPE,
) -> ChannelAgentBuildOutcome:
    """``build_channel_execution_agent`` for ``msg``, every other argument at its plain default."""
    return await build_channel_execution_agent(
        msg,
        query=query,
        is_resume=is_resume,
        configs=configs or minimal_user_configs(),
        memory_settings=memory_settings or {},
        embedding_cfg=None,
        reranker_cfg=None,
        mcp_configs=None,
        lite_model_cfg=None,
        fallback_model_cfg=None,
        fallback_lite_model_cfg=None,
        vision_fallback_model_cfg=None,
        user_instructions="",
        chat_id="chat-db-id",
        session_key="telegram:chat-1",
        resolved_agent_id=None,
        resolved_profile=None,
        agent_skill_ids=[],
        agent_subagent_ids=None,
        agent_max_iterations=None,
        agent_engine_params=None,
        enabled_builtin_tools=enabled_builtin_tools or ["code_execution"],
        auto_restore_domains=[],
        memory_decay_profile=None,
        memory_scope=memory_scope,
    )


async def build_live_turn(msg: InboundMessage, *, is_resume: bool = False) -> tuple[ChannelAgentBuildResult, GeneralAgentParams]:
    """The turn ``build_channel_execution_agent`` assembles for ``msg``, and the params its agent was created from."""
    captured: dict[str, GeneralAgentParams] = {}

    def _capture_create_agent(params: GeneralAgentParams) -> MagicMock:
        captured["params"] = params
        return MagicMock()

    with (
        patch(
            "app.services.memory.shared_context.shared_context.resolve_shared_context_ids",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.core.channel_bridge.agent_executor.execute_preamble.agent.AgentFactory.create_general_agent",
            side_effect=_capture_create_agent,
        ),
        patch(
            "app.services.agent.session_credential_assembler.assemble_session_credentials",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        outcome = await build_agent(msg, is_resume=is_resume)

    assert outcome.result is not None
    return outcome.result, captured["params"]
