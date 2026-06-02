"""Compaction 熔断机制测试

直接验证 SummarizeProcessor 的 circuit breaker 逻辑，
使用 ProcessorContext 注入 mock LLM 而非启动完整 Agent 流水线。
"""

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from myrm_agent_harness.agent.context_management.pipeline.processors.summarize_processor import (
    MAX_CONSECUTIVE_SUMMARIZE_FAILURES,
    SummarizeProcessor,
    _is_circuit_open,
    _set_failures,
)
from myrm_agent_harness.observability.metrics.circuit_breaker_metrics import (
    circuit_breaker_state,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    _set_failures(0)
    circuit_breaker_state.labels(component="summarize").set(0)
    circuit_breaker_state.labels(component="session_notes").set(0)
    yield
    _set_failures(0)
    circuit_breaker_state.labels(component="summarize").set(0)
    circuit_breaker_state.labels(component="session_notes").set(0)


def _build_large_messages(count: int = 100) -> list[HumanMessage | AIMessage]:
    msgs: list[HumanMessage | AIMessage] = []
    for _ in range(count):
        msgs.append(HumanMessage(content="Hello " * 500))
        msgs.append(AIMessage(content="Hi " * 500))
    return msgs


def _make_processor_context(
    messages: list[HumanMessage | AIMessage],
    llm: object,
) -> "ProcessorContext":
    """Build a minimal ProcessorContext for SummarizeProcessor."""
    from myrm_agent_harness.agent.context_management.pipeline.base import (
        ProcessorContext,
    )

    return ProcessorContext(
        messages=list(messages),
        user_query="test",
        llm=llm,
        summarizer_llm=llm,
        merged_context={},
        metadata={},
    )


@pytest.mark.asyncio
async def test_summarize_circuit_breaker_auth_failure():
    """连续 auth 失败应触发熔断（circuit breaker OPEN）"""
    messages = _build_large_messages()

    mock_llm = AsyncMock()
    mock_llm.ainvoke.side_effect = Exception("401 Unauthorized")

    processor = SummarizeProcessor()

    with patch(
        "myrm_agent_harness.agent.context_management.pipeline.processors.summarize_processor.should_summarize",
        return_value=True,
    ):
        for _ in range(MAX_CONSECUTIVE_SUMMARIZE_FAILURES):
            ctx = _make_processor_context(messages, mock_llm)
            await processor.process(ctx)

    assert _is_circuit_open(), "Circuit breaker should be OPEN after repeated auth failures"
    final_state = circuit_breaker_state.labels(component="summarize")._value.get()
    assert final_state == 2.0, f"Expected 2.0 (OPEN), got {final_state}"


@pytest.mark.asyncio
async def test_summarize_circuit_breaker_timeout():
    """连续 timeout 失败应触发熔断"""
    messages = _build_large_messages()

    mock_llm = AsyncMock()
    mock_llm.ainvoke.side_effect = TimeoutError("Timeout")

    processor = SummarizeProcessor()

    with patch(
        "myrm_agent_harness.agent.context_management.pipeline.processors.summarize_processor.should_summarize",
        return_value=True,
    ):
        for _ in range(MAX_CONSECUTIVE_SUMMARIZE_FAILURES):
            ctx = _make_processor_context(messages, mock_llm)
            await processor.process(ctx)

    assert _is_circuit_open(), "Circuit breaker should be OPEN after repeated timeouts"
    final_state = circuit_breaker_state.labels(component="summarize")._value.get()
    assert final_state == 2.0, f"Expected 2.0 (OPEN), got {final_state}"


@pytest.mark.asyncio
async def test_session_notes_manager_circuit_breaker():
    """测试 SessionNotesManager 的熔断机制"""
    from langchain_core.messages import HumanMessage
    from myrm_agent_harness.agent.context_management.strategies.session_notes.schemas import SessionNotesConfig
    from myrm_agent_harness.agent.context_management.strategies.session_notes.updater import SessionNotesManager

    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=Exception("401 Unauthorized"))

    config = SessionNotesConfig(
        init_token_threshold=100,
        update_token_threshold=100,
        max_consecutive_failures=3,
    )
    manager = SessionNotesManager(llm=llm, config=config)

    msgs = [HumanMessage(content="hello " * 100)]

    await manager.maybe_trigger_update(msgs, total_tokens=200, total_tool_calls=0)
    await asyncio.sleep(0.1)

    assert manager._is_circuit_open() is True
    assert circuit_breaker_state.labels(component="session_notes")._value.get() == 2.0
