"""Builders shared by the length-truncation recovery tests."""

from unittest.mock import MagicMock

from myrm_agent_harness.agent.streaming.stream_executor import StreamContext, StreamExecutor

from ..scripted_agent import RecordingCompactor


def make_executor(ctx: StreamContext) -> StreamExecutor:
    executor = StreamExecutor(ctx=ctx, fallback_llm=None, rebuild_agent_fn=None, safety_fallback_llm=None)
    executor._compactor = RecordingCompactor()
    return executor


def llm_with_max_tokens(value: int | None) -> MagicMock:
    """Build an LLM stub whose configured output budget is ``value``."""
    llm = MagicMock()
    llm.max_tokens = value
    llm.model_kwargs = {}
    llm.model_name = "unknown-model"
    return llm
