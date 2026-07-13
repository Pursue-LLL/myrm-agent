"""Regression tests for execute_preamble agent early-exit paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.types import InboundMessage, OutboundMessage
from app.core.channel_bridge.agent_executor.execute_preamble_agent import (
    build_channel_execution_agent,
)
from app.core.channel_bridge.config_loader import UserConfigs
from app.core.types.business import ModelConfig


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
    }


@pytest.mark.asyncio
async def test_build_agent_rejects_resume_when_approval_timeout_already_resolved() -> None:
    msg = _inbound_message(resume_value={"type": "approve"})
    mock_agent = MagicMock()

    with (
        patch(
            "app.core.channel_bridge.agent_executor.execute_preamble_agent.AgentFactory.create_general_agent",
            return_value=mock_agent,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.approval.scheduler.ApprovalTimeoutScheduler.get",
        ) as mock_scheduler_get,
    ):
        mock_scheduler_get.return_value.resolve_if_first.return_value = False
        result = await build_channel_execution_agent(
            **_agent_build_kwargs(
                msg,
                is_resume=True,
                configs=_minimal_user_configs(),
                enabled_builtin_tools=["code_execution"],
            ),
        )

    assert isinstance(result, tuple)
    assert len(result) == 1
    reply = result[0]
    assert isinstance(reply, OutboundMessage)
    assert "approval" in reply.content.lower() or "审批" in reply.content


@pytest.mark.asyncio
async def test_build_agent_returns_search_unreachable_when_service_down() -> None:
    msg = _inbound_message()

    with patch(
        "app.core.channel_bridge.agent_executor.execute_preamble_agent.verify_search_service_available",
        new_callable=AsyncMock,
        return_value=False,
    ):
        result = await build_channel_execution_agent(
            **_agent_build_kwargs(
                msg,
                is_resume=False,
                configs=_minimal_user_configs(search_configured=True),
                enabled_builtin_tools=["web_search", "code_execution"],
            ),
        )

    assert isinstance(result, tuple)
    assert len(result) == 1
    reply = result[0]
    assert isinstance(reply, OutboundMessage)
    assert "search" in reply.content.lower() or "搜索" in reply.content


@pytest.mark.asyncio
async def test_build_agent_returns_search_not_configured_when_missing_service() -> None:
    msg = _inbound_message(locale="zh-CN")

    result = await build_channel_execution_agent(
        **_agent_build_kwargs(
            msg,
            is_resume=False,
            configs=_minimal_user_configs(search_configured=False),
            enabled_builtin_tools=["web_search"],
        ),
    )

    assert isinstance(result, tuple)
    reply = result[0]
    assert isinstance(reply, OutboundMessage)
    assert "搜索" in reply.content
