"""Regression tests for execute_preamble agent early-exit paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.ai_agents.agents import GeneralAgentParams
from app.channels.routing.identity_scope import TurnMemoryScope
from app.channels.types import InboundMessage, OutboundMessage
from app.core.channel_bridge.agent_executor.execute_preamble.agent import (
    build_channel_execution_agent,
)
from app.core.channel_bridge.agent_executor.execute_preamble.types import (
    ChannelAgentBuildOutcome,
    ChannelAgentBuildResult,
)
from app.core.channel_bridge.config_loader import UserConfigs
from app.core.channel_bridge.learn_handler import LEARN_PROMPT_PREFIX
from app.core.types.business import ModelConfig

_OWNER_MEMORY_SCOPE = TurnMemoryScope(policy=None, extra_namespaces=(), is_compartment=False)


def _inbound_message(*, resume_value: object | None = None, locale: str = "en") -> InboundMessage:
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


def _minimal_user_configs(*, search_configured: bool = False) -> UserConfigs:
    return UserConfigs(
        model_cfg=ModelConfig(model="test-model", api_key="test-key"),
        search_cfg={"url": "http://127.0.0.1:8080"} if search_configured else None,
        search_is_user_configured=search_configured,
        retrieval_dict=None,
        personal_settings_dict={},
        mcp_dict=None,
        providers_dict=None,
    )


def _agent_build_kwargs(
    msg: InboundMessage,
    *,
    is_resume: bool,
    configs: UserConfigs,
    enabled_builtin_tools: list[str],
) -> dict[str, object]:
    return {
        "msg": msg,
        "query": "test query",
        "is_resume": is_resume,
        "configs": configs,
        "memory_settings": {},
        "embedding_cfg": None,
        "reranker_cfg": None,
        "mcp_configs": None,
        "lite_model_cfg": None,
        "fallback_model_cfg": None,
        "fallback_lite_model_cfg": None,
        "vision_fallback_model_cfg": None,
        "user_instructions": "",
        "chat_id": "chat-db-id",
        "session_key": "telegram:chat-1",
        "resolved_agent_id": None,
        "resolved_profile": None,
        "agent_skill_ids": [],
        "agent_subagent_ids": None,
        "agent_max_iterations": None,
        "agent_engine_params": None,
        "enabled_builtin_tools": enabled_builtin_tools,
        "auto_restore_domains": [],
        "memory_decay_profile": None,
        "memory_scope": _OWNER_MEMORY_SCOPE,
    }


@pytest.mark.asyncio
async def test_build_agent_rejects_resume_when_approval_timeout_already_resolved() -> None:
    msg = _inbound_message(resume_value={"type": "approve"})

    with (
        patch(
            "app.core.channel_bridge.agent_executor.execute_preamble.agent.AgentFactory.create_general_agent",
        ) as mock_create_agent,
        patch(
            "myrm_agent_harness.agent.middlewares.approval.scheduler.ApprovalTimeoutScheduler.get",
        ) as mock_scheduler_get,
    ):
        mock_scheduler_get.return_value.resolve_if_first.return_value = False
        outcome = await build_channel_execution_agent(
            **_agent_build_kwargs(
                msg,
                is_resume=True,
                configs=_minimal_user_configs(),
                enabled_builtin_tools=["code_execution"],
            ),
        )

    mock_create_agent.assert_not_called()
    assert outcome.result is None
    assert outcome.early_reply is not None
    assert isinstance(outcome.early_reply, OutboundMessage)
    assert "approval" in outcome.early_reply.content.lower() or "审批" in outcome.early_reply.content


_RESUME_APPROVAL_KEY = "telegram:chat-1"


async def _build_resume_with_failure(
    *,
    create_agent_error: Exception | None = None,
    credentials_error: Exception | None = None,
) -> ChannelAgentBuildOutcome:
    """Build a resume turn against the real scheduler; the failing stage is selected by the caller."""
    with (
        patch(
            "app.services.memory.shared_context.shared_context.resolve_shared_context_ids",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.core.channel_bridge.agent_executor.execute_preamble.agent.AgentFactory.create_general_agent",
            side_effect=create_agent_error,
            return_value=MagicMock(),
        ),
        patch(
            "app.services.agent.session_credential_assembler.assemble_session_credentials",
            new_callable=AsyncMock,
            side_effect=credentials_error,
            return_value=[],
        ),
    ):
        return await build_channel_execution_agent(
            **_agent_build_kwargs(
                _inbound_message(resume_value={"type": "approve"}),
                is_resume=True,
                configs=_minimal_user_configs(),
                enabled_builtin_tools=["code_execution"],
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_stage", ["create_agent", "credentials"])
async def test_build_agent_reopens_resume_claim_when_assembly_fails(failing_stage: str) -> None:
    scheduler = ApprovalTimeoutScheduler.get()
    scheduler.reopen(_RESUME_APPROVAL_KEY)
    failure = RuntimeError("assembly failed")

    try:
        with pytest.raises(RuntimeError, match="assembly failed"):
            await _build_resume_with_failure(
                create_agent_error=failure if failing_stage == "create_agent" else None,
                credentials_error=failure if failing_stage == "credentials" else None,
            )
        assert scheduler.resolve_if_first(_RESUME_APPROVAL_KEY) is True
    finally:
        scheduler.reopen(_RESUME_APPROVAL_KEY)


@pytest.mark.asyncio
async def test_build_agent_keeps_resume_claim_after_successful_assembly() -> None:
    scheduler = ApprovalTimeoutScheduler.get()
    scheduler.reopen(_RESUME_APPROVAL_KEY)

    try:
        outcome = await _build_resume_with_failure()
        assert outcome.result is not None
        assert scheduler.resolve_if_first(_RESUME_APPROVAL_KEY) is False
    finally:
        scheduler.reopen(_RESUME_APPROVAL_KEY)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expect_force_skill_manage"),
    [
        (f"{LEARN_PROMPT_PREFIX} Save it with the `skill_manage_tool`.", True),
        ("What is in this picture?", False),
    ],
)
async def test_build_agent_accepts_multimodal_query(text: str, expect_force_skill_manage: bool) -> None:
    query: list[dict[str, object]] = [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
    ]
    kwargs = _agent_build_kwargs(
        _inbound_message(),
        is_resume=False,
        configs=_minimal_user_configs(),
        enabled_builtin_tools=["code_execution"],
    )
    kwargs["query"] = query

    with (
        patch(
            "app.services.memory.shared_context.shared_context.resolve_shared_context_ids",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.core.channel_bridge.agent_executor.execute_preamble.agent.AgentFactory.create_general_agent",
            return_value=MagicMock(),
        ) as mock_create_agent,
        patch(
            "app.services.agent.session_credential_assembler.assemble_session_credentials",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        outcome = await build_channel_execution_agent(**kwargs)

    assert outcome.result is not None
    assert outcome.result.query_input == query
    assert mock_create_agent.call_args.args[0].force_skill_manage is expect_force_skill_manage


@pytest.mark.asyncio
async def test_build_agent_returns_search_unreachable_when_service_down() -> None:
    msg = _inbound_message()

    with patch(
        "app.core.channel_bridge.agent_executor.execute_preamble.agent.verify_search_service_available",
        new_callable=AsyncMock,
        return_value=False,
    ):
        outcome = await build_channel_execution_agent(
            **_agent_build_kwargs(
                msg,
                is_resume=False,
                configs=_minimal_user_configs(search_configured=True),
                enabled_builtin_tools=["web_search", "code_execution"],
            ),
        )

    assert outcome.result is None
    assert outcome.early_reply is not None
    assert isinstance(outcome.early_reply, OutboundMessage)
    assert "search" in outcome.early_reply.content.lower() or "搜索" in outcome.early_reply.content


@pytest.mark.asyncio
async def test_build_agent_returns_search_not_configured_when_missing_service() -> None:
    msg = _inbound_message(locale="zh-CN")

    outcome = await build_channel_execution_agent(
        **_agent_build_kwargs(
            msg,
            is_resume=False,
            configs=_minimal_user_configs(search_configured=False),
            enabled_builtin_tools=["web_search"],
        ),
    )

    assert outcome.result is None
    assert outcome.early_reply is not None
    assert isinstance(outcome.early_reply, OutboundMessage)
    assert "搜索" in outcome.early_reply.content


@pytest.mark.asyncio
async def test_build_agent_passes_message_locale_to_general_agent_params() -> None:
    msg = _inbound_message(locale="en")
    captured: dict[str, object] = {}

    def _capture_create_agent(params: object) -> MagicMock:
        captured["locale"] = getattr(params, "locale", None)
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
        outcome = await build_channel_execution_agent(
            **_agent_build_kwargs(
                msg,
                is_resume=False,
                configs=_minimal_user_configs(),
                enabled_builtin_tools=["code_execution"],
            ),
        )

    assert outcome.result is not None
    assert captured["locale"] == "en"


async def _build_params_with_memory_scope(memory_scope: TurnMemoryScope) -> GeneralAgentParams:
    captured: dict[str, GeneralAgentParams] = {}

    def _capture_create_agent(params: GeneralAgentParams) -> MagicMock:
        captured["params"] = params
        return MagicMock()

    kwargs = _agent_build_kwargs(
        _inbound_message(),
        is_resume=False,
        configs=_minimal_user_configs(),
        enabled_builtin_tools=["code_execution"],
    )
    kwargs["memory_scope"] = memory_scope
    kwargs["memory_settings"] = {"enableMemory": True, "memoryEnableConversationSearch": True}

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
        outcome = await build_channel_execution_agent(**kwargs)

    assert outcome.result is not None
    return captured["params"]


@pytest.mark.asyncio
async def test_build_agent_confines_compartment_turn_memory_and_recall() -> None:
    from app.core.memory.adapters.policy import compartment_memory_policy

    scope = TurnMemoryScope(
        policy=compartment_memory_policy(None),
        extra_namespaces=("ident:telegram-chat-1-channel",),
        is_compartment=True,
    )

    params = await _build_params_with_memory_scope(scope)

    assert params.memory_policy == scope.policy
    assert params.memory_extra_namespaces == ["ident:telegram-chat-1-channel"]
    assert params.enable_conversation_search is False


@pytest.mark.asyncio
async def test_build_agent_keeps_owner_turn_memory_and_recall() -> None:
    params = await _build_params_with_memory_scope(_OWNER_MEMORY_SCOPE)

    assert params.memory_policy is None
    assert params.memory_extra_namespaces == []
    assert params.enable_conversation_search is True


def test_channel_agent_build_outcome_rejects_invalid_xor_states() -> None:
    with pytest.raises(ValueError, match="exactly one of result or early_reply"):
        ChannelAgentBuildOutcome()

    mock_reply = OutboundMessage(
        channel="telegram",
        recipient_id="chat-1",
        content="blocked",
        user_id="user-1",
    )
    mock_result = ChannelAgentBuildResult(
        agent=MagicMock(),
        token_ctx=MagicMock(),
        query_input="query",
        params=MagicMock(),
    )
    with pytest.raises(ValueError, match="exactly one of result or early_reply"):
        ChannelAgentBuildOutcome(result=mock_result, early_reply=mock_reply)
