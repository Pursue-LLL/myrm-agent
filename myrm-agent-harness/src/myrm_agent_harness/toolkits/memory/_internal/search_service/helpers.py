"""[INPUT]
- memory 的时间窗与观测码（POS: 检索告警与时间窗类型）

[OUTPUT]
- 时间窗 metadata、告警码、后台任务失败日志与耗时格式化

[POS]
`memory/_internal/search_service/` 的纯函数助手；不持有服务状态。
"""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import TYPE_CHECKING, Literal

from myrm_agent_harness.toolkits.memory._internal.temporal_window import TemporalWindow
from myrm_agent_harness.toolkits.memory.observability import (
    GATHER_BM25_FAILED,
    GATHER_BM25_TIMEOUT,
    GATHER_CONVERSATION_FAILED,
    GATHER_CONVERSATION_TIMEOUT,
    GATHER_EPISODIC_FAILED,
    GATHER_EPISODIC_TIMEOUT,
    GATHER_GRAPH_FAILED,
    GATHER_GRAPH_TIMEOUT,
    GATHER_PROCEDURAL_FAILED,
    GATHER_PROCEDURAL_TIMEOUT,
    GATHER_PROFILE_FAILED,
    GATHER_PROFILE_TIMEOUT,
    GATHER_QUERY_EMBEDDING_FAILED,
    GATHER_QUERY_EMBEDDING_TIMEOUT,
    GATHER_SEMANTIC_FAILED,
    GATHER_SEMANTIC_TIMEOUT,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


_STREAM_WARNING_MAP: dict[str, tuple[str, str]] = {
    "query_embedding": (GATHER_QUERY_EMBEDDING_TIMEOUT, GATHER_QUERY_EMBEDDING_FAILED),
    "profile": (GATHER_PROFILE_TIMEOUT, GATHER_PROFILE_FAILED),
    "procedural": (GATHER_PROCEDURAL_TIMEOUT, GATHER_PROCEDURAL_FAILED),
    "semantic": (GATHER_SEMANTIC_TIMEOUT, GATHER_SEMANTIC_FAILED),
    "episodic": (GATHER_EPISODIC_TIMEOUT, GATHER_EPISODIC_FAILED),
    "conversation": (GATHER_CONVERSATION_TIMEOUT, GATHER_CONVERSATION_FAILED),
    "bm25": (GATHER_BM25_TIMEOUT, GATHER_BM25_FAILED),
    "graph": (GATHER_GRAPH_TIMEOUT, GATHER_GRAPH_FAILED),
}

def _temporal_window_metadata(window: TemporalWindow | None) -> dict[str, str] | None:
    """Trace-friendly view of a derived temporal window (None when not derived)."""
    if window is None:
        return None
    return {
        "marker": window.marker,
        "kind": window.window_kind,
        "since": window.since.isoformat(),
        "until": window.until.isoformat(),
    }


def _stream_warning_code(stream: str, failure_type: Literal["timeout", "failed"]) -> str:
    codes = _STREAM_WARNING_MAP.get(stream)
    if not codes:
        return f"GATHER_{stream.upper()}_{failure_type.upper()}"
    return codes[0] if failure_type == "timeout" else codes[1]


def _log_background_task_failure(task: asyncio.Task[object]) -> None:
    if task.cancelled():
        return
    try:
        exc = task.exception()
    except Exception as err:
        logger.warning("Memory background task exception lookup failed: %s", err)
        return
    if exc is not None:
        logger.warning("Memory background task failed: %s", exc)


def _elapsed_ms(start: float) -> float:
    return round((perf_counter() - start) * 1000, 3)
