"""A clock a test moves forward by hand, as the cache decisions of the context pipeline read it.

[INPUT]
- agent.context_management.infra.cache_break_detector (POS: times the gap since the last model call)
- agent.context_management.infra.cache_metrics_collector::clear_cache_usage_feedback (POS: the provider's cache figures of a run)
- agent.context_management.pipeline.processors.cache_ttl_prune_processor (POS: judges from that gap whether the prompt cache has expired)
- agent.context_management.pipeline.processors.compress_processor, summarize_processor.processor (POS: hold a compaction back while the prompt cache is hot)
- agent.middlewares.context_pipeline.context_pipeline_middleware (POS: stamps the time of the last successful model call)

[OUTPUT]
- VirtualClock: real time plus an offset the test advances
- virtual_clock: the clock the modules above read, for the length of the block
- start_run: what the start of a run does to the cache state it runs in

[POS]
The provider's prompt cache lapses with the wall clock and the pipeline prunes by how long ago the last model call
was. A test cannot wait minutes for that; moving the clock those modules read reproduces an idle gap at once, while
asyncio and the HTTP stack keep real time.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

from myrm_agent_harness.agent.context_management.infra import cache_break_detector
from myrm_agent_harness.agent.context_management.infra.cache_metrics_collector import clear_cache_usage_feedback
from myrm_agent_harness.agent.context_management.pipeline.processors import (
    cache_ttl_prune_processor,
    compress_processor,
)
from myrm_agent_harness.agent.context_management.pipeline.processors.summarize_processor import (
    processor as summarize_processor,
)
from myrm_agent_harness.agent.middlewares.context_pipeline import context_pipeline_middleware


@dataclass(slots=True)
class VirtualClock:
    """Real time plus ``offset`` seconds."""

    offset: float = 0.0

    def advance(self, seconds: float) -> None:
        self.offset += seconds


@contextmanager
def virtual_clock() -> Iterator[VirtualClock]:
    clock = VirtualClock()
    shim = SimpleNamespace(
        time=lambda: time.time() + clock.offset,
        monotonic=lambda: time.monotonic() + clock.offset,
        perf_counter=time.perf_counter,
    )
    with (
        patch.object(cache_break_detector, "time", shim),
        patch.object(context_pipeline_middleware, "time", shim),
        patch.object(cache_ttl_prune_processor, "time", shim),
        patch.object(compress_processor, "time", shim),
        patch.object(summarize_processor, "time", shim),
    ):
        yield clock


def start_run() -> None:
    """A run starts with a fresh detector and none of the cache figures an earlier run of this process collected."""
    cache_break_detector.init_cache_break_detector()
    clear_cache_usage_feedback()
