"""Shared builders for the preamble tests.

An inbound message, user configs, ``build_channel_execution_agent`` with every argument but the varying ones at its plain
default, the params its agent is created from, the turn it assembles for a message, and the preamble itself with every
collaborator stood in for.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from myrm_agent_harness.agent.security import CredentialTrack
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.ai_agents.agents import GeneralAgentParams
from app.channels.routing.identity_scope import TurnMemoryScope
from app.channels.types import InboundMessage, OutboundMessage, SessionPolicy, TopicContext
from app.core.channel_bridge.agent_executor.execute_preamble.agent import build_channel_execution_agent
from app.core.channel_bridge.agent_executor.execute_preamble.preamble import prepare_channel_execution
from app.core.channel_bridge.agent_executor.execute_preamble.session import ChannelSessionContext
from app.core.channel_bridge.agent_executor.execute_preamble.types import ChannelAgentBuildOutcome, ChannelAgentBuildResult
from app.core.channel_bridge.config_loader import UserConfigs
from app.core.channel_bridge.wake_return import WakeOrigins
from app.core.types.business import MCPServerConfig, ModelConfig
from app.services.agent.profile.profile_resolver import ResolvedAgentProfile

_PREAMBLE = "app.core.channel_bridge.agent_executor.execute_preamble.preamble"

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
    credential_track: CredentialTrack = CredentialTrack.PERSONAL,
    resolved_profile: ResolvedAgentProfile | None = None,
    mcp_configs: list[MCPServerConfig] | None = None,
    fallback_model_cfg: ModelConfig | None = None,
    fallback_lite_model_cfg: ModelConfig | None = None,
    vision_fallback_model_cfg: ModelConfig | None = None,
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
        mcp_configs=mcp_configs,
        lite_model_cfg=None,
        fallback_model_cfg=fallback_model_cfg,
        fallback_lite_model_cfg=fallback_lite_model_cfg,
        vision_fallback_model_cfg=vision_fallback_model_cfg,
        user_instructions="",
        chat_id="chat-db-id",
        session_key="telegram:chat-1",
        resolved_agent_id=None,
        resolved_profile=resolved_profile,
        agent_skill_ids=[],
        agent_subagent_ids=None,
        agent_max_iterations=None,
        agent_engine_params=None,
        enabled_builtin_tools=enabled_builtin_tools or ["code_execution"],
        auto_restore_domains=[],
        memory_decay_profile=None,
        memory_scope=memory_scope,
        credential_track=credential_track,
    )


@contextmanager
def captured_agent_params() -> Iterator[dict[str, GeneralAgentParams]]:
    """Stand in for the agent factory and the collaborators that need a database; yields the params the agent is created from."""
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
        yield captured


async def build_live_turn(
    msg: InboundMessage,
    *,
    is_resume: bool = False,
    configs: UserConfigs | None = None,
    query: str | list[dict[str, object]] = "test query",
) -> tuple[ChannelAgentBuildResult, GeneralAgentParams]:
    """The turn ``build_channel_execution_agent`` assembles for ``msg``, and the params its agent was created from."""
    with captured_agent_params() as captured:
        outcome = await build_agent(msg, is_resume=is_resume, configs=configs, query=query)

    assert outcome.result is not None
    return outcome.result, captured["params"]


@dataclass(frozen=True)
class PreambleProbe:
    """What the preamble asked of its collaborators: the agent build, the agent-profile lookups and the session resolution."""

    builder: AsyncMock
    profiles: MagicMock
    session: AsyncMock


@contextmanager
def stubbed_preamble() -> Iterator[PreambleProbe]:
    """``prepare_channel_execution`` with every collaborator stood in for; the agent build ends the turn with an early reply."""
    early_reply = OutboundMessage(channel="feishu", recipient_id="chat9", content="stop here", user_id="")
    builder = AsyncMock(return_value=ChannelAgentBuildOutcome(early_reply=early_reply))
    profiles = MagicMock()
    profiles.resolve = AsyncMock(return_value=None)
    session = AsyncMock(
        return_value=ChannelSessionContext(
            session_key="telegram:chat-1",
            chat_id="chat-db-1",
            chat_history=[],
            session_was_auto_reset=False,
            session_policy=SessionPolicy(),
            query="hi",
            pre_events=(),
        )
    )
    with (
        patch(f"{_PREAMBLE}.get_wake_origins", return_value=WakeOrigins()),
        patch("app.services.budget.enforcer.should_block_execution", AsyncMock(return_value=False)),
        patch("app.services.budget.channel_budget.should_block_channel", return_value=False),
        patch(f"{_PREAMBLE}.load_user_configs", AsyncMock(return_value=minimal_user_configs())),
        patch(f"{_PREAMBLE}.get_agent_profile_resolver", return_value=profiles),
        patch(f"{_PREAMBLE}.enrich_channel_user_instructions", AsyncMock(return_value="")),
        patch(f"{_PREAMBLE}.resolve_channel_session_context", session),
        patch(f"{_PREAMBLE}.build_channel_execution_agent", builder),
    ):
        yield PreambleProbe(builder=builder, profiles=profiles, session=session)


async def prepare(msg: InboundMessage, topic: TopicContext | None) -> None:
    """Run the preamble for ``msg`` served by ``topic`` (inside ``stubbed_preamble``)."""
    await prepare_channel_execution(AsyncMock(), msg, is_resume=False, topic_context=topic, untrusted_sender=False)
