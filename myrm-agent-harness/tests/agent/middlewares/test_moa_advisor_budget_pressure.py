"""Budget pressure silences the advisor round, and the toast that says so is shown once."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage

from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import create_moa_advisor_middleware
from myrm_agent_harness.toolkits.llms.consensus.moa_overlay_types import MoAOverlayConfig


@pytest.mark.asyncio
async def test_middleware_emits_overlay_skipped_on_budget_pressure() -> None:
    mock_llm = MagicMock(model_name="ref-a")
    middleware = create_moa_advisor_middleware(
        [mock_llm],
        config=MoAOverlayConfig(fanout="user_turn"),
        unattended=False,
    )
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))
    skip_mock = AsyncMock()
    run_mock = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware._budget_pressure_active",
            return_value=True,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware._emit_overlay_skipped",
            skip_mock,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware.AdvisorFanoutRunner.run",
            run_mock,
        ),
    ):
        await middleware.awrap_model_call(request, handler)

    skip_mock.assert_awaited_once_with("budget_pressure")
    run_mock.assert_not_called()
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_middleware_budget_skip_toast_emits_once_per_turn() -> None:
    mock_llm = MagicMock(model_name="ref-a")
    middleware = create_moa_advisor_middleware(
        [mock_llm],
        config=MoAOverlayConfig(fanout="per_iteration"),
        unattended=False,
    )
    request = ModelRequest(messages=[HumanMessage(content="hello")], model=mock_llm)
    handler = AsyncMock(return_value=ModelResponse(result=MagicMock()))
    skip_mock = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware._budget_pressure_active",
            return_value=True,
        ),
        patch(
            "myrm_agent_harness.agent.middlewares.moa_advisor_middleware._emit_overlay_skipped",
            skip_mock,
        ),
    ):
        await middleware.awrap_model_call(request, handler)
        await middleware.awrap_model_call(request, handler)

    skip_mock.assert_awaited_once_with("budget_pressure")


def test_budget_pressure_active_tracker_none() -> None:
    from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
        _budget_pressure_active,
    )

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=None,
    ):
        assert _budget_pressure_active() is False


def test_budget_pressure_active_status_ok() -> None:
    from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
        _budget_pressure_active,
    )

    tracker = MagicMock()
    tracker.last_budget_status = "ok"
    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker,
    ):
        assert _budget_pressure_active() is False


def test_budget_pressure_active_status_pressure() -> None:
    from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
        _budget_pressure_active,
    )

    tracker = MagicMock()
    tracker.last_budget_status = "high"
    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker,
    ):
        assert _budget_pressure_active() is True


def test_budget_pressure_active_exception_safe() -> None:
    from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
        _budget_pressure_active,
    )

    def _raise():
        raise RuntimeError("tracker down")

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        side_effect=_raise,
    ):
        assert _budget_pressure_active() is False
