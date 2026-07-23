"""Integration tests for POOLED execution cache in stream_pipeline."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_agents.general_agent.agent import GeneralAgent
from app.ai_agents.general_agent.stream_pipeline import execute_stream_pipeline
from app.core.types import ModelConfig
from app.services.agent.execution_cache import ExecutionMode, finalize_agent_session, get_execution_cache


@pytest.fixture(autouse=True)
async def _reset_execution_cache_singleton() -> None:
    await get_execution_cache().close_all()
    yield
    await get_execution_cache().close_all()


async def _collect_pipeline_events(
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


@pytest.mark.asyncio
async def test_pooled_same_chat_builds_once_across_two_messages() -> None:
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
        chat_id="chat-pool-1",
        agent_id="agent-a",
    )
    build_count = 0
    skill_agent = MagicMock()

    async def fake_run(
        *_args: object,
        **_kwargs: object,
    ) -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "message", "data": "ok"}

    skill_agent.run = fake_run
    skill_agent.memory_manager = None

    async def fake_build(
        agent_wrapper: GeneralAgent,
        effective_chat_id: str,
        user_id: str | None = None,
    ) -> MagicMock:
        nonlocal build_count
        build_count += 1
        agent_wrapper.agent = skill_agent
        return skill_agent

    @asynccontextmanager
    async def noop_async_context(*_args: object, **_kwargs: object):
        yield

    with (
        patch("app.ai_agents.general_agent.factory.build_general_agent", side_effect=fake_build),
        patch.object(
            wrapper,
            "_build_runtime_context",
            return_value={"session_id": "sess-1", "query": "hello"},
        ),
        patch("app.platform_utils.get_artifact_processor") as artifact_mock,
        patch(
            "app.ai_agents.general_agent.agent_middlewares.tool_selection_middleware.reset_answer_tool_convergence",
        ),
        patch("app.services.infra.sleep_inhibitor.SleepInhibitor.hold", noop_async_context),
        patch(
            "app.services.web_fetch.binding.open_web_fetch_escalation_context",
            noop_async_context,
        ),
    ):
        artifact_mock.return_value.process_artifacts_ready = MagicMock()

        await _collect_pipeline_events(wrapper, chat_id="chat-pool-1", query="first")
        await finalize_agent_session(
            wrapper,
            chat_id="chat-pool-1",
            agent_id="agent-a",
            extra_context={"execution_mode": ExecutionMode.POOLED},
        )

        await _collect_pipeline_events(wrapper, chat_id="chat-pool-1", query="second")
        await finalize_agent_session(
            wrapper,
            chat_id="chat-pool-1",
            agent_id="agent-a",
            extra_context={"execution_mode": ExecutionMode.POOLED},
        )

    assert build_count == 1


@pytest.mark.asyncio
async def test_ephemeral_same_chat_rebuilds_each_message() -> None:
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
        chat_id="chat-ephemeral-1",
    )
    build_count = 0
    skill_agent = MagicMock()
    skill_agent.close = AsyncMock()

    async def fake_run(
        *_args: object,
        **_kwargs: object,
    ) -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "message", "data": "ok"}

    skill_agent.run = fake_run
    skill_agent.memory_manager = None

    async def fake_build(
        agent_wrapper: GeneralAgent,
        effective_chat_id: str,
        user_id: str | None = None,
    ) -> MagicMock:
        nonlocal build_count
        build_count += 1
        agent_wrapper.agent = skill_agent
        return skill_agent

    @asynccontextmanager
    async def noop_async_context(*_args: object, **_kwargs: object):
        yield

    with (
        patch("app.ai_agents.general_agent.factory.build_general_agent", side_effect=fake_build),
        patch.object(
            wrapper,
            "_build_runtime_context",
            return_value={"session_id": "sess-2", "query": "hello"},
        ),
        patch("app.platform_utils.get_artifact_processor") as artifact_mock,
        patch(
            "app.ai_agents.general_agent.agent_middlewares.tool_selection_middleware.reset_answer_tool_convergence",
        ),
        patch("app.services.infra.sleep_inhibitor.SleepInhibitor.hold", noop_async_context),
        patch(
            "app.services.web_fetch.binding.open_web_fetch_escalation_context",
            noop_async_context,
        ),
    ):
        artifact_mock.return_value.process_artifacts_ready = MagicMock()

        async for _ in execute_stream_pipeline(
            wrapper,
            query="first",
            chat_id="chat-ephemeral-1",
            extra_context={"execution_mode": ExecutionMode.EPHEMERAL},
        ):
            pass
        await finalize_agent_session(
            wrapper,
            chat_id="chat-ephemeral-1",
            agent_id=None,
            extra_context={"execution_mode": ExecutionMode.EPHEMERAL},
        )

        async for _ in execute_stream_pipeline(
            wrapper,
            query="second",
            chat_id="chat-ephemeral-1",
            extra_context={"execution_mode": ExecutionMode.EPHEMERAL},
        ):
            pass

    assert build_count == 2
    skill_agent.close.assert_awaited()


@pytest.mark.asyncio
async def test_pooled_stream_seeds_yolo_security_context_before_run() -> None:
    """Per-agent YOLO must reach approval middleware ContextVar before SkillAgent.run()."""
    from myrm_agent_harness.agent.security.types import SecurityConfig
    from myrm_agent_harness.agent.types import AgentRuntimeConfig

    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
        chat_id="chat-yolo-ctx",
        agent_id="agent-yolo",
        agent_security_raw={"yoloModeEnabled": True, "yolo_mode_enabled_at": 1_700_000_000.0},
        security_config_raw={"yoloModeEnabled": False},
    )
    skill_agent = MagicMock()
    skill_agent.config = AgentRuntimeConfig(
        security_config=SecurityConfig(ruleset=(), yolo_mode_enabled=False),
    )

    async def fake_run(
        *_args: object,
        **_kwargs: object,
    ) -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "message", "data": "ok"}

    skill_agent.run = fake_run
    skill_agent.memory_manager = None
    wrapper.agent = skill_agent

    seeded: list[SecurityConfig | None] = []

    def _capture_seed(config: SecurityConfig | None) -> None:
        seeded.append(config)

    async def fake_build(
        agent_wrapper: GeneralAgent,
        effective_chat_id: str,
        user_id: str | None = None,
    ) -> MagicMock:
        agent_wrapper.agent = skill_agent
        return skill_agent

    @asynccontextmanager
    async def noop_async_context(*_args: object, **_kwargs: object):
        yield

    with (
        patch("app.ai_agents.general_agent.factory.build_general_agent", side_effect=fake_build),
        patch.object(
            wrapper,
            "_build_runtime_context",
            return_value={"session_id": "sess-yolo", "query": "hello"},
        ),
        patch(
            "myrm_agent_harness.agent.middlewares._session_context.set_security_config",
            side_effect=_capture_seed,
        ),
        patch(
            "app.ai_agents.extensions.security_policy_extension.sync_wrapper_security_from_store",
            new=AsyncMock(),
        ),
        patch("app.services.infra.sleep_inhibitor.SleepInhibitor.hold", noop_async_context),
        patch("app.services.web_fetch.binding.open_web_fetch_escalation_context", noop_async_context),
    ):
        async for _ in execute_stream_pipeline(
            wrapper,
            query="run bash",
            chat_id="chat-yolo-ctx",
            extra_context={"execution_mode": ExecutionMode.POOLED},
        ):
            pass

    assert seeded, "expected set_security_config before SkillAgent.run"
    assert seeded[0] is not None
    assert seeded[0].yolo_mode_enabled is True
