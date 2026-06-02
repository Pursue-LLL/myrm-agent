"""Regression tests for daily budget block SSE shape in general agent streaming."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.ai_agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.streaming import ai_agent_service_stream


def _minimal_params() -> GeneralAgentParams:
    return GeneralAgentParams(
        query="hello",
        model_cfg=ModelConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key="test-key",
        ),
        search_service_cfg=SearchServiceConfig(search_service="tavily"),
        chat_id="chat-budget-test",
        message_id="msg-budget-test",
    )


@pytest.mark.asyncio
async def test_ai_agent_service_stream_yields_budget_blocked_events() -> None:
    with patch(
        "app.services.budget.enforcer.should_block_execution",
        new_callable=AsyncMock,
        return_value=True,
    ):
        events = [event async for event in ai_agent_service_stream(_minimal_params())]

    assert len(events) == 2
    assert events[0]["type"] == "message"
    assert events[0]["data"] == ""
    assert events[1]["type"] == "message_end"
    assert events[1]["completion_status"] == "budget_blocked"


@pytest.mark.asyncio
async def test_ai_agent_service_stream_does_not_start_agent_when_blocked() -> None:
    with (
        patch(
            "app.services.budget.enforcer.should_block_execution",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch("app.services.agent.streaming.AgentFactory.create_general_agent") as create_agent,
    ):
        events = [event async for event in ai_agent_service_stream(_minimal_params())]

    create_agent.assert_not_called()
    assert events[-1]["completion_status"] == "budget_blocked"
