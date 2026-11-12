"""The Compress step starts at the configured compress_start_ratio, like the Summarize step does."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage

from myrm_agent_harness.agent.context_management.infra.schemas import ContextConfig
from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.engine import build_default_processors
from myrm_agent_harness.agent.context_management.pipeline.processors.compress_processor import CompressProcessor

_WINDOW = 200_000


def _compress_processor(ratio: float | None) -> CompressProcessor:
    processors = build_default_processors(max_context_tokens=_WINDOW, compress_start_ratio=ratio)
    return next(p for p in processors if isinstance(p, CompressProcessor))


def _context() -> ProcessorContext:
    return ProcessorContext(
        messages=[HumanMessage(content="hi")],
        user_query="hi",
        user_id="user-1",
        chat_id="compress-start-ratio",
        metadata={},
    )


def test_threshold_follows_the_configured_ratio() -> None:
    default_threshold = _compress_processor(None).config.compress_threshold
    delayed_threshold = _compress_processor(0.8).config.compress_threshold

    assert default_threshold == int(_WINDOW * 0.5)
    assert delayed_threshold == ContextConfig(max_context_tokens=_WINDOW, compress_start_ratio=0.8).compress_threshold
    assert delayed_threshold > default_threshold


@pytest.mark.asyncio
async def test_a_higher_ratio_postpones_compression() -> None:
    # 120K tokens are above the default start (50% = 100K) and below the start a ratio of 0.8 gives (about 170K).
    with patch.object(CompressProcessor, "_estimate_context_tokens", return_value=120_000):
        assert await _compress_processor(None).should_process(_context()) is True
        assert await _compress_processor(0.8).should_process(_context()) is False
