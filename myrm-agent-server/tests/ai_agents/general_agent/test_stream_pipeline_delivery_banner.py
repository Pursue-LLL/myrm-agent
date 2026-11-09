"""The stream pipeline hands the agent the turn as typed in the browser chat, and bannered with its route elsewhere.

The browser chat is the default ingress and its route never varies, so a banner there would cost a constant line and
the disclaimer that goes with it on every turn. A scheduled job, an eval run, a wake-up or an IM channel arrives by a
route the model can tell apart, so its turn carries the banner.
"""

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


@pytest.fixture(autouse=True)
def _mock_security_store_sync() -> None:
    with patch(
        "app.ai_agents.extensions.security_policy_extension.sync_wrapper_security_from_store",
        new=AsyncMock(),
    ):
        yield


async def _turn_handed_to_the_agent(channel_name: str, typed: str) -> object:
    """Run one turn of an agent on ``channel_name`` through the pipeline and return the query its run was handed."""
    from myrm_agent_harness.agent.security.types import SecurityConfig
    from myrm_agent_harness.agent.types import AgentRuntimeConfig

    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
        chat_id="chat-banner",
        channel_name=channel_name,
    )
    skill_agent = MagicMock()
    skill_agent.config = AgentRuntimeConfig(security_config=SecurityConfig(ruleset=()))
    skill_agent.memory_manager = None
    skill_agent.close = AsyncMock()
    handed: list[object] = []

    async def fake_run(query: object, **_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        handed.append(query)
        yield {"type": "message", "data": "ok"}

    skill_agent.run = fake_run

    async def fake_build(agent_wrapper: GeneralAgent, effective_chat_id: str, user_id: str | None = None) -> MagicMock:
        agent_wrapper.agent = skill_agent
        return skill_agent

    @asynccontextmanager
    async def noop_async_context(*_args: object, **_kwargs: object):
        yield

    with (
        patch("app.ai_agents.general_agent.factory.build_general_agent", side_effect=fake_build),
        patch.object(wrapper, "_build_runtime_context", return_value={"session_id": "sess-banner", "query": typed}),
        patch("app.platform_utils.get_artifact_processor") as artifact_mock,
        patch("app.ai_agents.general_agent.agent_middlewares.tool_selection_middleware.reset_answer_tool_convergence"),
        patch("app.services.infra.sleep_inhibitor.SleepInhibitor.hold", noop_async_context),
        patch("app.services.web_fetch.binding.open_web_fetch_escalation_context", noop_async_context),
    ):
        artifact_mock.return_value.process_artifacts_ready = MagicMock()
        extra_context = {"execution_mode": ExecutionMode.EPHEMERAL}
        async for _ in execute_stream_pipeline(wrapper, query=typed, chat_id="chat-banner", extra_context=extra_context):
            pass
        await finalize_agent_session(wrapper, chat_id="chat-banner", agent_id=None, extra_context=extra_context)

    assert len(handed) == 1
    return handed[0]


@pytest.mark.asyncio
async def test_a_browser_chat_turn_reaches_the_agent_as_typed() -> None:
    assert await _turn_handed_to_the_agent("web_chat", "hello") == "hello"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("channel_name", "labels"),
    [
        ("cron", "channel=cron ingress=cron_scheduler"),
        ("headless_wakeup", "channel=headless_wakeup ingress=async_wake_consumer"),
        ("telegram", "channel=telegram ingress=server_pipeline"),
    ],
)
async def test_a_turn_from_any_other_channel_reaches_the_agent_with_its_route(channel_name: str, labels: str) -> None:
    handed = await _turn_handed_to_the_agent(channel_name, "hello")

    assert isinstance(handed, str)
    assert handed.startswith(f"[Inbound channel message] {labels}\n")
    assert handed.endswith("\n\nhello")
