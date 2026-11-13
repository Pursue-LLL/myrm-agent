"""Integration: a context pipeline saving, however often it recurs, leaves the run's guards alone.

The pipeline reports a saving on many model calls: every prune and every cleaned tool result counts, and the request
view is rebuilt from the same history on each call, so the same saving shows up again. LoopGuard's window belongs to
the run's tool calls and the read-before-edit gate records what the model read; neither changes when the view of
the context shrinks.

No real LLM required: a stub compressor stands in for the pruning processors.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.pipeline import ContextPipeline, ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.base import BaseProcessor
from myrm_agent_harness.agent.meta_tools.file_ops.core.file_integrity_guard import get_file_integrity_guard
from myrm_agent_harness.agent.middlewares.context_pipeline.context_pipeline_middleware import (
    create_context_pipeline_middleware,
)
from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import _loop_guard_var
from myrm_agent_harness.agent.security.guards.loop_guard import LoopAction, LoopGuard


class _FakeCompressor(BaseProcessor):
    """Trims the request view to its last four messages and reports the saving, on every call."""

    name = "fake_compress"

    async def should_process(self, context: ProcessorContext) -> bool:
        return len(context.messages) > 4

    async def process(self, context: ProcessorContext) -> ProcessorContext:
        saved = len(context.messages) - 4
        context.messages = context.messages[-4:]
        context.tokens_saved += saved * 200
        context.operations.append("compress")
        return context


def _long_conversation(rounds: int = 12) -> list:
    messages: list = []
    for i in range(rounds):
        messages.append(HumanMessage(content=f"Task {i}: run tests"))
        messages.append(
            AIMessage(
                content="Running...",
                tool_calls=[{"id": f"call_{i}", "name": "bash_code_execute_tool", "args": {"cmd": f"pytest t{i}.py"}}],
            )
        )
        messages.append(ToolMessage(content="PASSED", tool_call_id=f"call_{i}", name="bash_code_execute_tool"))
    return messages


async def _model_call_with_saving() -> None:
    llm = MagicMock()
    llm.model = "test-model"
    llm.api_base = ""
    middleware = create_context_pipeline_middleware(llm=llm, pipeline=ContextPipeline([_FakeCompressor()]))
    request = ModelRequest(model=llm, messages=_long_conversation())
    await middleware.awrap_model_call(request, AsyncMock(return_value=MagicMock()))


@pytest.fixture
def loop_guard():
    guard = LoopGuard()
    token = _loop_guard_var.set(guard)
    yield guard
    _loop_guard_var.reset(token)


@pytest.mark.asyncio
async def test_a_repeating_tool_call_is_caught_while_every_model_call_reports_a_saving(loop_guard: LoopGuard) -> None:
    verdicts = []
    for _ in range(12):
        await _model_call_with_saving()
        verdicts.append(loop_guard.pre_check("bash_code_execute_tool", {"cmd": "pytest tests/test_x.py"}))

    assert any(verdict.action is not LoopAction.ALLOW for verdict in verdicts)


@pytest.mark.asyncio
async def test_the_loop_guard_keeps_its_window_counts_and_signatures_through_repeated_savings(
    loop_guard: LoopGuard,
) -> None:
    for i in range(10):
        loop_guard.pre_check(f"tool_{i}", {"i": i})
    loop_guard._error_signatures["crash://db-timeout"] = 3

    for _ in range(3):
        await _model_call_with_saving()

    assert len(loop_guard.recorded_calls()) == 10
    assert loop_guard.get_metrics().total_calls == 10
    assert loop_guard._error_signatures["crash://db-timeout"] == 3


@pytest.mark.asyncio
async def test_a_file_read_before_a_saving_stays_open_for_editing_after_it(loop_guard: LoopGuard) -> None:
    executor = MagicMock()
    guard = get_file_integrity_guard(executor)
    assert guard is not None
    guard.record_read("/w/app.py", "x = 1\n")

    await _model_call_with_saving()
    await _model_call_with_saving()

    assert guard.require_read_before_write("/w/app.py") is None
    assert guard.require_full_read_before_edit("/w/app.py") is None


@pytest.mark.asyncio
async def test_a_file_never_read_stays_closed_for_editing(loop_guard: LoopGuard) -> None:
    executor = MagicMock()
    guard = get_file_integrity_guard(executor)
    assert guard is not None

    await _model_call_with_saving()

    assert guard.require_read_before_write("/w/never_read.py") is not None
