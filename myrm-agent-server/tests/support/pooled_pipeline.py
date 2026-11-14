"""Drive execute_stream_pipeline in POOLED mode without a live server behind it."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import MagicMock, patch

from app.ai_agents.general_agent.agent import GeneralAgent
from app.ai_agents.general_agent.stream_pipeline import execute_stream_pipeline
from app.services.agent.execution_cache import ExecutionMode


def skill_agent_mock() -> MagicMock:
    from myrm_agent_harness.agent.security.types import SecurityConfig
    from myrm_agent_harness.agent.types import AgentRuntimeConfig

    skill_agent = MagicMock()
    skill_agent.config = AgentRuntimeConfig(security_config=SecurityConfig(ruleset=()))
    skill_agent.memory_manager = None
    return skill_agent


@asynccontextmanager
async def _noop_async_context(*_args: object, **_kwargs: object) -> AsyncIterator[None]:
    yield


@contextmanager
def stubbed_pipeline_edges(*, session_id: str) -> Iterator[None]:
    """Replace the collaborators of a pipeline run that only exist in a running server."""
    with (
        patch.object(GeneralAgent, "_build_runtime_context", return_value={"session_id": session_id, "query": "hello"}),
        patch("app.platform_utils.get_artifact_processor") as artifact_mock,
        patch("app.ai_agents.general_agent.agent_middlewares.tool_selection_middleware.reset_answer_tool_convergence"),
        patch("app.services.infra.sleep_inhibitor.SleepInhibitor.hold", _noop_async_context),
        patch("app.services.web_fetch.binding.open_web_fetch_escalation_context", _noop_async_context),
    ):
        artifact_mock.return_value.process_artifacts_ready = MagicMock()
        yield


async def collect_pipeline_events(
    wrapper: GeneralAgent,
    *,
    chat_id: str,
    query: str = "hello",
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    async for event in execute_stream_pipeline(
        wrapper,
        query=query,
        chat_id=chat_id,
        extra_context={"execution_mode": ExecutionMode.POOLED},
    ):
        events.append(event)
    return events
