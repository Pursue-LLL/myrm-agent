"""Integration test: Deep Research wiki vault callback wiring.

Verifies the full chain: create_deep_research_stream with enable_wiki=True
correctly constructs and passes the on_report_ready callback to the orchestrator.
No real LLM calls — validates wiring only.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.stream_session.stream_lane_factory import create_deep_research_stream


@pytest.mark.asyncio
async def test_wiki_callback_passed_to_orchestrator_when_enabled() -> None:
    """create_deep_research_stream passes on_report_ready when enable_wiki=True."""
    captured_kwargs: dict[str, object] = {}

    mock_orch = MagicMock()

    async def _empty_run(**kwargs):  # type: ignore[no-untyped-def]
        return
        yield

    mock_orch.run = _empty_run

    def capture_orch_init(**kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return mock_orch

    mock_llm = MagicMock()
    mock_search_tool = MagicMock()

    params = MagicMock()
    params.enable_wiki = True
    params.chat_id = "test-chat"
    params.message_id = "msg-1"
    params.model_cfg = MagicMock()
    params.model_cfg.api_keys = None
    params.search_service_cfg = MagicMock()
    params.query = "Research quantum computing"
    params.chat_history = None
    params.channel_name = None

    with (
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "myrm_agent_harness.toolkits.create_web_search_tool",
            return_value=mock_search_tool,
        ),
        patch(
            "app.services.budget.enforcer.should_block_execution",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("app.services.budget.enforcer.reset_session_budget"),
        patch(
            "myrm_agent_harness.agent.deep_research.DeepResearchOrchestrator",
            side_effect=capture_orch_init,
        ),
    ):
        events = []
        async for event in create_deep_research_stream(params=params, cancel_token=None):
            events.append(event)
            if len(events) > 3:
                break

    assert "on_report_ready" in captured_kwargs
    assert captured_kwargs["on_report_ready"] is not None
    assert callable(captured_kwargs["on_report_ready"])


@pytest.mark.asyncio
async def test_wiki_callback_not_passed_when_disabled() -> None:
    """create_deep_research_stream does NOT pass on_report_ready when enable_wiki=False."""
    captured_kwargs: dict[str, object] = {}

    mock_orch = MagicMock()

    async def _empty_run(**kwargs):  # type: ignore[no-untyped-def]
        return
        yield

    mock_orch.run = _empty_run

    def capture_orch_init(**kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return mock_orch

    mock_llm = MagicMock()
    mock_search_tool = MagicMock()

    params = MagicMock()
    params.enable_wiki = False
    params.chat_id = "test-chat"
    params.message_id = "msg-2"
    params.model_cfg = MagicMock()
    params.model_cfg.api_keys = None
    params.search_service_cfg = MagicMock()
    params.query = "Research quantum computing"
    params.chat_history = None
    params.channel_name = None

    with (
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "myrm_agent_harness.toolkits.create_web_search_tool",
            return_value=mock_search_tool,
        ),
        patch(
            "app.services.budget.enforcer.should_block_execution",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("app.services.budget.enforcer.reset_session_budget"),
        patch(
            "myrm_agent_harness.agent.deep_research.DeepResearchOrchestrator",
            side_effect=capture_orch_init,
        ),
    ):
        events = []
        async for event in create_deep_research_stream(params=params, cancel_token=None):
            events.append(event)
            if len(events) > 3:
                break

    assert captured_kwargs.get("on_report_ready") is None
