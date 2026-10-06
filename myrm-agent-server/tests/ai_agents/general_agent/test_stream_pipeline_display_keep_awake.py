"""流式管线的休眠抑制单测 — 挂载桌面会话的运行必须保持显示器常亮。

[INPUT]
- app.ai_agents.general_agent.stream_pipeline.execute_stream_pipeline（POS: 流式执行管线，持有休眠抑制）
- app.services.infra.sleep_inhibitor.SleepInhibitor（POS: 引用计数休眠抑制，此处以录制替身观察入参）

[OUTPUT]
- 挂载桌面会话 → hold(prevent_display_sleep=True)；未挂载 → hold(prevent_display_sleep=False)

[POS]
空闲熄屏会把屏幕锁住，Computer Use 任务因此中断；显示器常亮需求只对真正挂载了
桌面会话的运行成立，纯文本运行不额外占用显示器。
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


async def _run_once(*, desktop_session: object | None) -> list[bool]:
    """跑一轮管线，返回每次 SleepInhibitor.hold 收到的 prevent_display_sleep。"""
    from myrm_agent_harness.agent.security.types import SecurityConfig
    from myrm_agent_harness.agent.types import AgentRuntimeConfig

    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
        chat_id="chat-keep-awake",
    )
    skill_agent = MagicMock()
    skill_agent.config = AgentRuntimeConfig(security_config=SecurityConfig(ruleset=()))
    skill_agent.memory_manager = None
    skill_agent.close = AsyncMock()

    async def fake_run(*_args: object, **_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "message", "data": "ok"}

    skill_agent.run = fake_run

    async def fake_build(agent_wrapper: GeneralAgent, effective_chat_id: str, user_id: str | None = None) -> MagicMock:
        agent_wrapper.agent = skill_agent
        agent_wrapper._desktop_session = desktop_session
        return skill_agent

    hold_calls: list[bool] = []

    @asynccontextmanager
    async def recording_hold(prevent_display_sleep: bool = False):
        hold_calls.append(prevent_display_sleep)
        yield

    @asynccontextmanager
    async def noop_async_context(*_args: object, **_kwargs: object):
        yield

    with (
        patch("app.ai_agents.general_agent.factory.build_general_agent", side_effect=fake_build),
        patch.object(wrapper, "_build_runtime_context", return_value={"session_id": "sess-ka", "query": "hello"}),
        patch("app.platform_utils.get_artifact_processor") as artifact_mock,
        patch("app.ai_agents.general_agent.agent_middlewares.tool_selection_middleware.reset_answer_tool_convergence"),
        patch("app.services.infra.sleep_inhibitor.SleepInhibitor.hold", recording_hold),
        patch("app.services.web_fetch.binding.open_web_fetch_escalation_context", noop_async_context),
    ):
        artifact_mock.return_value.process_artifacts_ready = MagicMock()
        extra_context = {"execution_mode": ExecutionMode.EPHEMERAL}
        async for _ in execute_stream_pipeline(wrapper, query="hello", chat_id="chat-keep-awake", extra_context=extra_context):
            pass
        await finalize_agent_session(wrapper, chat_id="chat-keep-awake", agent_id=None, extra_context=extra_context)
    return hold_calls


@pytest.mark.asyncio
async def test_run_with_desktop_session_keeps_display_awake() -> None:
    assert await _run_once(desktop_session=MagicMock()) == [True]


@pytest.mark.asyncio
async def test_run_without_desktop_session_does_not_hold_display() -> None:
    assert await _run_once(desktop_session=None) == [False]
