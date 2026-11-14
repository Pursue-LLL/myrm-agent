"""Which unit the pooled stream pipeline runs a turn on, with the production factory and builder.

A chat served by an interactive unit and then run unattended must get the unit an unattended run builds, and
consecutive goal turns, which differ only in the YOLO stamp the trigger rewrites, must share one unit. The tool
set of each unit is the real one. The pipeline runs inside the scope's turn guard, and no prewarm precedes these
turns, so the unit can only be swapped by the pipeline's own acquire.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Iterator
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from myrm_agent_harness.agent.middlewares.approval.batch_processor import is_yolo_mode_active
from myrm_agent_harness.agent.security.types import SecurityConfig
from myrm_agent_harness.api import SkillAgent

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.ai_agents.general_agent import GeneralAgent
from app.core.types.business import ModelConfig
from app.platform_utils import _reset_checkpointer_for_testing, set_checkpointer
from app.services.agent.execution_cache import ExecutionMode, finalize_agent_session, get_execution_cache
from app.services.agent.goals.goal_registry import GoalRegistry
from tests.support.pooled_pipeline import collect_pipeline_events, stubbed_pipeline_edges


@pytest.fixture(autouse=True)
def _checkpointer() -> Iterator[None]:
    set_checkpointer(InMemorySaver())
    yield
    _reset_checkpointer_for_testing()


@pytest.fixture(autouse=True)
async def _reset_execution_cache_singleton() -> AsyncGenerator[None, None]:
    await get_execution_cache().close_all()
    yield
    await get_execution_cache().close_all()


@pytest.fixture(autouse=True)
def _stub_pipeline_edges() -> Iterator[None]:
    async def run_without_llm(self: SkillAgent, *_args: object, **_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "message", "data": "ok"}

    with (
        patch("app.ai_agents.extensions.security_policy_extension.sync_wrapper_security_from_store", new=AsyncMock()),
        patch.object(SkillAgent, "run", run_without_llm),
        stubbed_pipeline_edges(session_id="sess-unit-selection"),
    ):
        yield


def _wrapper(chat_id: str, *, unattended: bool) -> GeneralAgent:
    return AgentFactory.create_general_agent(
        GeneralAgentParams(
            model_cfg=ModelConfig(model="gpt-4o", api_key="test-key"),
            query="weekly report",
            chat_id=chat_id,
            enable_browser=False,
            enable_memory=False,
            enable_web_search=False,
            enable_structured_clarify=True,
            unattended_mode=unattended,
            channel_name="cron" if unattended else "web_chat",
        )
    )


async def _run_turn(chat_id: str, *, unattended: bool) -> set[str]:
    """Run one pooled turn and return the tool names of the unit it ran on."""
    wrapper = _wrapper(chat_id, unattended=unattended)
    await collect_pipeline_events(wrapper, chat_id=chat_id)
    assert wrapper.agent is not None
    await wrapper.agent._ensure_initialized()
    tool_names = {tool.name for tool in wrapper.agent._cached_tools or []}
    await finalize_agent_session(
        wrapper,
        chat_id=chat_id,
        agent_id=None,
        extra_context={"execution_mode": ExecutionMode.POOLED},
    )
    return tool_names


def _goal_wrapper(chat_id: str, *, yolo_stamp: float, agent_security_raw: dict[str, object] | None) -> GeneralAgent:
    """A wrapper as the goal trigger builds it: unattended, with YOLO forced on and stamped."""
    return AgentFactory.create_general_agent(
        GeneralAgentParams(
            model_cfg=ModelConfig(model="gpt-4o", api_key="test-key"),
            query="weekly report",
            chat_id=chat_id,
            enable_browser=False,
            enable_memory=False,
            enable_web_search=False,
            unattended_mode=True,
            security_config_raw={"yolo_mode_enabled": True, "yolo_mode_enabled_at": yolo_stamp, "yolo_mode_timeout": None},
            agent_security_raw=agent_security_raw,
        )
    )


async def _run_goal_turn(
    chat_id: str, *, yolo_stamp: float, agent_security_raw: dict[str, object] | None = None
) -> tuple[SkillAgent, SecurityConfig]:
    """Run one pooled goal turn; return the agent of the unit it ran on and the security config it ran under."""
    wrapper = _goal_wrapper(chat_id, yolo_stamp=yolo_stamp, agent_security_raw=agent_security_raw)
    await collect_pipeline_events(wrapper, chat_id=chat_id)
    agent = wrapper.agent
    assert agent is not None
    security = agent.config.security_config
    assert security is not None
    await finalize_agent_session(
        wrapper,
        chat_id=chat_id,
        agent_id=None,
        extra_context={"execution_mode": ExecutionMode.POOLED},
    )
    return agent, security


@pytest.mark.asyncio
async def test_a_chat_follows_its_mode_when_it_flips_between_interactive_and_unattended() -> None:
    cold_unattended = await _run_turn("chat-flip-cold", unattended=True)

    interactive = await _run_turn("chat-flip", unattended=False)
    unattended = await _run_turn("chat-flip", unattended=True)
    interactive_again = await _run_turn("chat-flip", unattended=False)

    # The interactive unit carries the structured-clarify tool, so reusing it unattended would mount it there.
    assert "ask_question_tool" in interactive
    assert unattended == cold_unattended
    assert interactive_again == interactive


@pytest.mark.asyncio
async def test_an_unattended_turn_that_resumes_a_goal_gets_the_goal_tools_an_interactive_unit_lacks() -> None:
    chat_id = "chat-flip-goal"
    interactive = await _run_turn(chat_id, unattended=False)
    await GoalRegistry.get_or_create_provider(chat_id).create_goal(session_id=chat_id, objective="ship the weekly report")
    try:
        resumed = await _run_turn(chat_id, unattended=True)
    finally:
        GoalRegistry.unregister(chat_id)

    assert not {"complete_goal_tool", "todo_write"} & interactive
    assert {"complete_goal_tool", "todo_write"} <= resumed
    assert "ask_question_tool" not in resumed


@pytest.mark.asyncio
async def test_goal_turns_that_differ_only_in_the_yolo_stamp_share_one_unit_that_runs_under_the_latest_stamp() -> None:
    """The stamp is not a build input, and the pipeline re-applies the security config every turn: the second
    turn reuses the first turn's unit and still runs under its own stamp."""
    chat_id = "chat-goal-stamp"
    await GoalRegistry.get_or_create_provider(chat_id).create_goal(session_id=chat_id, objective="ship the weekly report")
    try:
        first_agent, first_security = await _run_goal_turn(chat_id, yolo_stamp=1_700_000_000.0)
        second_agent, second_security = await _run_goal_turn(chat_id, yolo_stamp=1_700_000_030.0)
    finally:
        GoalRegistry.unregister(chat_id)

    assert second_agent is first_agent
    assert (first_security.yolo_mode_enabled_at, second_security.yolo_mode_enabled_at) == (1_700_000_000.0, 1_700_000_030.0)


@pytest.mark.asyncio
async def test_a_reused_unit_under_an_agent_yolo_timeout_judges_expiry_by_the_latest_stamp() -> None:
    """An agent's YOLO timeout counts from the stamp the trigger rewrites on every run. The stamp is not a build
    input, so the second turn reuses the unit, and the stamp it runs under, not the first turn's, decides whether
    YOLO is still on."""
    chat_id = "chat-goal-agent-timeout"
    timeout = 600
    agent_yolo: dict[str, object] = {"yoloModeEnabled": True, "yolo_mode_timeout": timeout}
    now = time.time()
    await GoalRegistry.get_or_create_provider(chat_id).create_goal(session_id=chat_id, objective="ship the weekly report")
    try:
        first_agent, first_security = await _run_goal_turn(chat_id, yolo_stamp=now - 2 * timeout, agent_security_raw=agent_yolo)
        second_agent, second_security = await _run_goal_turn(chat_id, yolo_stamp=now, agent_security_raw=agent_yolo)
    finally:
        GoalRegistry.unregister(chat_id)

    assert second_agent is first_agent
    assert first_security.yolo_mode_timeout == second_security.yolo_mode_timeout == timeout
    assert not is_yolo_mode_active(first_security)
    assert is_yolo_mode_active(second_security)
