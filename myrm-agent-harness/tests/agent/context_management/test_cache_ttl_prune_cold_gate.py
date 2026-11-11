"""The cold-cache trigger of the TTL prune can be switched off per profile, and context pressure still prunes.

A prune that starts mid-run changes what an earlier signed reasoning block was written under, so the profile of a
route that signs reasoning (Claude) starts no prune because a cache looks cold. A window that is running out is a
different matter: that prune is needed whatever the route signs.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.infra.cache_policy import resolve_cache_ttl_prune_policy
from myrm_agent_harness.agent.context_management.infra.schemas import CacheTtlPruneConfig, CacheUsageFeedback
from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.processors.cache_ttl_prune_processor import (
    CacheTtlPruneProcessor,
)

_DETECTOR = (
    "myrm_agent_harness.agent.context_management.pipeline.processors.cache_ttl_prune_processor.get_cache_break_detector"
)
_OUTPUT_CHARS = 10_000
_OUTPUT = ("alpha beta gamma delta epsilon zeta eta theta " * 300)[:_OUTPUT_CHARS]
# The history below fills about 45% of this window: past the soft-trim ratio, well short of the emergency one.
_WINDOW = 44_000


def _history() -> list[BaseMessage]:
    messages: list[BaseMessage] = [HumanMessage(content="hi")]
    for i in range(10):
        messages.append(AIMessage(content=f"response_{i}"))
        messages.append(ToolMessage(content=_OUTPUT, tool_call_id=f"tc_{i}", name=f"tool_{i}"))
    return messages


def _context(metadata: dict[str, object]) -> ProcessorContext:
    return ProcessorContext(messages=_history(), user_query="test", metadata=metadata, merged_context={})


def _processor(*, enabled: bool, ttl_seconds: float = 300.0) -> CacheTtlPruneProcessor:
    config = CacheTtlPruneConfig(
        ttl_seconds=ttl_seconds,
        min_prunable_tokens=1000,
        keep_last_assistant_turns=1,
        cold_cache_prune_enabled=enabled,
    )
    return CacheTtlPruneProcessor(config=config, max_context_tokens=_WINDOW)


@pytest.mark.parametrize("enabled", [True, False])
async def test_an_idle_gap_starts_a_prune_only_while_the_trigger_is_on(enabled: bool) -> None:
    context = _context({"last_activity_time": time.time() - 400})

    with patch(_DETECTOR, return_value=None):
        assert await _processor(enabled=enabled).should_process(context) is enabled


@pytest.mark.parametrize("enabled", [True, False])
async def test_a_cold_hit_rate_in_the_provider_figures_starts_a_prune_only_while_the_trigger_is_on(
    enabled: bool,
) -> None:
    cold = CacheUsageFeedback(cache_hit_rate=0.0, cached_tokens=0, input_tokens=12_000, calls=3)
    context = _context({"last_activity_time": time.time(), "cache_usage_feedback": cold})

    assert await _processor(enabled=enabled, ttl_seconds=10_000).should_process(context) is enabled


async def test_a_window_that_is_running_out_prunes_with_the_trigger_off() -> None:
    config = CacheTtlPruneConfig(
        ttl_seconds=10_000,
        min_prunable_tokens=1000,
        keep_last_assistant_turns=1,
        emergency_prune_ratio=0.05,
        cold_cache_prune_enabled=False,
    )
    processor = CacheTtlPruneProcessor(config=config, max_context_tokens=_WINDOW)
    context = _context({"last_activity_time": time.time()})

    assert await processor.should_process(context) is True
    pruned = await processor.process(context)

    assert any(len(str(m.content)) < _OUTPUT_CHARS for m in pruned.messages if isinstance(m, ToolMessage))


@pytest.mark.parametrize(
    "model", ["anthropic/claude-sonnet-5-5", "claude-opus-5", "bedrock/anthropic.claude-sonnet-5-5-v1:0"]
)
def test_a_claude_route_starts_no_prune_for_a_cold_cache(model: str) -> None:
    assert resolve_cache_ttl_prune_policy(model).config.cold_cache_prune_enabled is False


@pytest.mark.parametrize(
    "model", ["gpt-4o", "gemini-2.5-pro", "deepseek-chat", "qwen3-max", "some-unlisted-model", None]
)
def test_every_other_route_keeps_the_trigger(model: str | None) -> None:
    assert resolve_cache_ttl_prune_policy(model).config.cold_cache_prune_enabled is True
