"""The risk-triggered advisor round: asked only when the router fires, and a hard timeout falls back silently."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage

from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import create_moa_advisor_middleware
from myrm_agent_harness.toolkits.llms.consensus.moa_overlay_types import MoAOverlayConfig
from myrm_agent_harness.toolkits.llms.consensus.types import ReferenceResponse


@pytest.mark.asyncio
async def test_risk_triggered_skips_when_no_risk() -> None:
    mock_llm = MagicMock(model_name="ref-a")
    middleware = create_moa_advisor_middleware(
        [mock_llm],
        config=MoAOverlayConfig(fanout="risk_triggered"),
        unattended=False,
    )
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))
    run_mock = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run",
            run_mock,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.advisor_risk_trigger_router.get_max_consecutive_replan_errors",
            return_value=0,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.advisor_risk_trigger_router.get_replan_error_summary",
            return_value={},
        ),
    ):
        await middleware.awrap_model_call(request, handler)

    run_mock.assert_not_called()
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_risk_triggered_fires_and_records_trigger() -> None:
    mock_llm = MagicMock(model_name="ref-a")
    mock_router = MagicMock()
    from myrm_agent_harness.agent.middlewares.advisor_risk_trigger_router import (
        RiskTriggerDecision,
        RiskTriggerReason,
    )

    mock_router.evaluate_trigger.return_value = RiskTriggerDecision(
        should_trigger=True,
        reason=RiskTriggerReason.CONSECUTIVE_TOOL_FAILURES,
        detail="Tool failed 2 times",
        risk_score=0.9,
    )

    middleware = create_moa_advisor_middleware(
        [mock_llm],
        config=MoAOverlayConfig(fanout="risk_triggered", min_successful=1),
        unattended=False,
        risk_router=mock_router,
    )
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))
    active_mock = AsyncMock()

    refs = [
        ReferenceResponse(
            model="ref-a",
            content="Advisor advice",
            elapsed_seconds=0.2,
            success=True,
        )
    ]

    with (
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run",
            new_callable=AsyncMock,
            return_value=refs,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware._emit_overlay_active",
            active_mock,
        ),
    ):
        await middleware.awrap_model_call(request, handler)

    mock_router.evaluate_trigger.assert_called_once()
    mock_router.record_trigger.assert_called_once()
    active_mock.assert_awaited_once_with(["ref-a"], trigger_reason="consecutive_tool_failures")
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_risk_triggered_hard_timeout_silent_fallback() -> None:
    mock_llm = MagicMock(model_name="ref-a")
    mock_router = MagicMock()
    from myrm_agent_harness.agent.middlewares.advisor_risk_trigger_router import (
        RiskTriggerDecision,
        RiskTriggerReason,
    )

    mock_router.evaluate_trigger.return_value = RiskTriggerDecision(
        should_trigger=True,
        reason=RiskTriggerReason.CONSECUTIVE_TOOL_FAILURES,
    )

    middleware = create_moa_advisor_middleware(
        [mock_llm],
        config=MoAOverlayConfig(fanout="risk_triggered", risk_trigger_timeout=0.01),
        unattended=False,
        risk_router=mock_router,
    )
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))
    skip_mock = AsyncMock()

    async def slow_fanout(*args, **kwargs):
        await asyncio.sleep(0.5)
        return []

    with (
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run",
            side_effect=slow_fanout,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware._emit_overlay_skipped",
            skip_mock,
        ),
    ):
        await middleware.awrap_model_call(request, handler)

    skip_mock.assert_awaited_once_with("risk_trigger_timeout")
    handler.assert_awaited_once()
