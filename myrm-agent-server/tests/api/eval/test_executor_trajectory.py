"""Unit tests for LocalEvalExecutor trajectory aggregation.

Verifies that the eval run discloses the agent's action trajectory back to
the report layer:
- ``limit_reached`` is captured from ``engine_limit_reached`` events
- ``blocked_count`` tallies steps rejected by the decontamination guard
  (``error_category == "benchmark_blocked"``)
- ``tool_call_details`` records per-step tool names, keys, and error text
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.eval.executor import LocalEvalExecutor


def _mock_stream(events: list[dict[str, object]]):
    async def mock_stream(*args, **kwargs):
        for event in events:
            yield event

    return mock_stream


def _executor(**kwargs) -> LocalEvalExecutor:
    return LocalEvalExecutor(benchmark_mode=True, **kwargs)


def _prepare_model_types() -> None:
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

    import app.ai_agents.agents as agent_types_mod
    from app.ai_agents.agents import GeneralAgentParams

    agent_types_mod.EmbeddingConfig = EmbeddingConfig
    agent_types_mod.RerankerConfig = RerankerConfig
    GeneralAgentParams.model_rebuild()


async def _run(executor: LocalEvalExecutor, events: list[dict[str, object]]):
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    from app.core.types import ModelConfig

    _prepare_model_types()
    with (
        patch("app.core.eval.executor.load_user_configs") as mock_configs,
        patch(
            "app.core.eval.executor.AgentFactory.create_general_agent"
        ) as mock_factory,
        patch(
            "app.services.agent.execution_cache.finalize_agent_session",
            new=AsyncMock(),
        ) as mock_finalize,
    ):
        mock_cfg = MagicMock()
        mock_cfg.retrieval_dict = {}
        mock_cfg.mcp_dict = {}
        mock_cfg.providers_dict = {}
        mock_cfg.personal_settings_dict = {}
        mock_cfg.model_cfg = ModelConfig(
            provider="test", model="test-model", apiKey="key"
        )
        mock_cfg.search_cfg = SearchServiceConfig(
            provider="tavily", searchService="tavily"
        )
        mock_cfg.search_is_user_configured = False
        mock_configs.return_value = mock_cfg

        mock_agent = MagicMock()
        mock_agent.process_stream = _mock_stream(events)
        mock_factory.return_value = mock_agent

        response = await executor.execute("Test task")
        mock_finalize.assert_awaited_once()
        return response


@pytest.mark.asyncio
async def test_limit_reached_captured_from_engine_event():
    """An engine_limit_reached event must surface the limit type in the response."""
    executor = _executor()
    response = await _run(
        executor,
        [
            {"type": "message", "data": "partial answer"},
            {
                "type": "engine_limit_reached",
                "data": {"limit_type": "max_tool_calls"},
            },
        ],
    )

    assert response.limit_reached == "max_tool_calls"


@pytest.mark.asyncio
async def test_no_limit_event_keeps_none():
    """A run that never hits a budget must report limit_reached as None."""
    executor = _executor()
    response = await _run(executor, [{"type": "message", "data": "answer"}])

    assert response.limit_reached is None


@pytest.mark.asyncio
async def test_blocked_steps_tallied():
    """Steps rejected by the decontamination guard must increment blocked_count."""
    executor = _executor()
    response = await _run(
        executor,
        [
            {
                "type": "tasks_steps",
                "tool_name": "web_search_tool",
                "step_key": "web_search_tool",
                "status": "error",
                "error_category": "benchmark_blocked",
                "error": "rejected by decontamination guard",
                "data": [{"k": "v"}],
            },
            {
                "type": "tasks_steps",
                "tool_name": "web_search_tool",
                "step_key": "web_search_tool",
                "status": "error",
                "error_category": "benchmark_blocked",
                "error": "rejected again",
                "data": [{"k": "v"}],
            },
            {
                "type": "tasks_steps",
                "tool_name": "web_fetch_tool",
                "step_key": "web_fetch_tool",
                "status": "ok",
                "data": [{"url": "https://example.com"}],
            },
        ],
    )

    assert response.blocked_count == 2


@pytest.mark.asyncio
async def test_blocked_count_zero_without_guard_errors():
    """Successful steps and non-guard errors must not count as blocked."""
    executor = _executor()
    response = await _run(
        executor,
        [
            {
                "type": "tasks_steps",
                "tool_name": "web_fetch_tool",
                "step_key": "web_fetch_tool",
                "status": "ok",
                "data": [{"url": "https://example.com"}],
            },
            {
                "type": "tasks_steps",
                "tool_name": "shell_tool",
                "step_key": "shell_tool",
                "status": "error",
                "error_category": "shell_error",
                "error": "exit code 1",
                "data": [{"cmd": "ls"}],
            },
        ],
    )

    assert response.blocked_count == 0


@pytest.mark.asyncio
async def test_tool_call_details_record_trajectory():
    """Each tasks_steps event must yield a per-step detail entry."""
    executor = _executor()
    response = await _run(
        executor,
        [
            {
                "type": "tasks_steps",
                "tool_name": "web_search_tool",
                "step_key": "web_search_tool",
                "data": [{"query": "open source"}],
            },
            {
                "type": "tasks_steps",
                "tool_name": "web_fetch_tool",
                "step_key": "web_fetch_tool",
                "status": "error",
                "error_category": "benchmark_blocked",
                "error": "rejected by decontamination guard",
                "data": [{"url": "https://huggingface.co/x"}],
            },
        ],
    )

    assert len(response.tool_call_details) == 2
    first = response.tool_call_details[0]
    assert first["tool_name"] == "web_search_tool"
    assert first["step_key"] == "web_search_tool"
    assert "error" not in first
    second = response.tool_call_details[1]
    assert second["tool_name"] == "web_fetch_tool"
    assert second["error"] == "rejected by decontamination guard"


@pytest.mark.asyncio
async def test_empty_trajectory_defaults():
    """A run with no task steps must report empty trajectory fields."""
    executor = _executor()
    response = await _run(executor, [{"type": "message", "data": "plain answer"}])

    assert response.limit_reached is None
    assert response.blocked_count == 0
    assert response.tool_call_details == []
