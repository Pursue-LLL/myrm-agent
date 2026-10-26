"""Wall-clock budget helpers for the memory search pipeline.

[INPUT]
- (none)

[OUTPUT]
- LOCAL_RECALL_RESERVE_FRACTION: Share of the retrieval budget the query embedding may never consume.
- deadline_remaining: Seconds left before a shared deadline, floored at zero.
- embedding_budget: Seconds the query embedding may use, keeping the local-recall reserve.

[POS]
Budget arithmetic shared by the embed / collect / graph stages of `MemorySearchService`.
Every network-touching stage draws from one deadline, so partial results gathered before it
survive while the pipeline still returns in bounded time. Not part of the public API.
"""

from __future__ import annotations

from time import perf_counter

# Share of the retrieval budget kept for the local stores (BM25 and dense lookup) while the
# query embedding is in flight, so a stalled embedding endpoint degrades recall to keyword
# hits instead of consuming the whole deadline and returning nothing.
LOCAL_RECALL_RESERVE_FRACTION = 0.25


def deadline_remaining(deadline: float) -> float:
    """Seconds left before ``deadline`` (a ``perf_counter`` instant), floored at zero."""
    return max(0.0, deadline - perf_counter())


def embedding_budget(deadline: float, total_seconds: float) -> float:
    """Seconds the query embedding may use: the time left minus the local-recall reserve."""
    return max(0.0, deadline_remaining(deadline) - total_seconds * LOCAL_RECALL_RESERVE_FRACTION)
