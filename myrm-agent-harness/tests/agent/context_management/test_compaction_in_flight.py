"""A compaction that falls due below the hard limit waits while the turn's signed reasoning blocks are in flight.

Compress and Summarize rewrite the messages a signed block is bound to. While the turn still carries blocks they hold
back below the hard limit even when the prompt cache has gone cold, leave the debt to the end of the turn, and run
at the hard limit as before.

[INPUT]
- agent.context_management.pipeline.processors.compress_processor::CompressProcessor (POS: the compress stage)
- agent.context_management.pipeline.processors.summarize_processor.processor::SummarizeProcessor (POS: the summarize stage)
- agent.context_management.tracking.task_metrics (POS: the compaction debt a turn leaves behind)
- core.thinking_blocks::THINKING_BLOCKS_KEY (POS: where a message keeps its signed reasoning blocks)

[POS]
Unit guard of the in-flight hold of both compaction stages: held below the hard limit, run at it, and unchanged
when no block is in flight.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.infra.schemas import ContextConfig
from myrm_agent_harness.agent.context_management.pipeline.base import BaseProcessor, ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.processors import compress_processor
from myrm_agent_harness.agent.context_management.pipeline.processors.compress_processor import CompressProcessor
from myrm_agent_harness.agent.context_management.pipeline.processors.summarize_processor import (
    processor as summarize_module,
)
from myrm_agent_harness.agent.context_management.pipeline.processors.summarize_processor.processor import (
    SummarizeProcessor,
)
from myrm_agent_harness.agent.context_management.tracking.task_metrics import clear_task_metrics, create_task_metrics
from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY

_CHAT_ID = "compaction-in-flight"
_WINDOW = 100_000
_DUE_AT = 40_000
# Past the five minutes a prompt stays cached.
_COLD_SECONDS = 400.0
_BLOCKS = [{"type": "thinking", "thinking": "plan", "signature": "sig"}]


@pytest.fixture(autouse=True)
def _fresh_metrics() -> Iterator[None]:
    clear_task_metrics(_CHAT_ID)
    yield
    clear_task_metrics(_CHAT_ID)


@pytest.fixture(params=["compress", "summarize"])
def stage(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Callable[[int], BaseProcessor]:
    """The compaction stage, built so that it is due at the token count it is given."""

    def build(tokens: int) -> BaseProcessor:
        if request.param == "compress":
            budget = SimpleNamespace(calculate_dynamic_thresholds=lambda **_: (_DUE_AT, 500))
            monkeypatch.setattr(compress_processor, "calculate_context_budget", lambda *_, **__: budget)
            monkeypatch.setattr(CompressProcessor, "_estimate_context_tokens", lambda self, context: tokens)
            return CompressProcessor(max_context_tokens=_WINDOW)
        monkeypatch.setattr(summarize_module, "should_summarize", lambda *_, **__: True)
        monkeypatch.setattr(summarize_module, "estimate_processor_context_tokens", lambda *_, **__: tokens)
        return SummarizeProcessor(config=ContextConfig(max_context_tokens=_WINDOW))

    return build


def _messages(*, signed: bool) -> list[BaseMessage]:
    kwargs = {THINKING_BLOCKS_KEY: _BLOCKS} if signed else {}
    call = {"id": "c1", "name": "grep_tool", "args": {}}
    return [
        HumanMessage(content="go"),
        AIMessage(content="", tool_calls=[call], additional_kwargs=kwargs),
        ToolMessage(content="found", name="grep_tool", tool_call_id="c1"),
    ]


def _cold_context(*, signed: bool) -> ProcessorContext:
    return ProcessorContext(
        messages=_messages(signed=signed),
        user_query="go",
        chat_id=_CHAT_ID,
        metadata={"last_activity_time": time.time() - _COLD_SECONDS},
    )


async def test_waits_on_a_cold_cache_while_signed_reasoning_is_in_flight(stage: Callable[[int], BaseProcessor]) -> None:
    metrics = create_task_metrics(_CHAT_ID)
    context = _cold_context(signed=True)

    assert await stage(60_000).should_process(context) is False

    assert context.metadata["compaction_debt_pending"] is True
    assert metrics.compaction_debt_pending is True


async def test_runs_at_the_hard_limit_while_signed_reasoning_is_in_flight(
    stage: Callable[[int], BaseProcessor],
) -> None:
    assert await stage(95_000).should_process(_cold_context(signed=True)) is True


async def test_runs_on_a_cold_cache_when_no_signed_reasoning_is_in_flight(
    stage: Callable[[int], BaseProcessor],
) -> None:
    context = _cold_context(signed=False)

    assert await stage(60_000).should_process(context) is True

    assert "compaction_debt_pending" not in context.metadata
