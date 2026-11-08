"""[INPUT]
- .offload::ContextOffloadResult / EvictedToolCall (POS: offload 类型)
- .summary::StructuredSummary (POS: 结构化摘要)

[OUTPUT]
- SummaryPersistCallback / ContextCompressOffloadCallback / ContextCompressEvictionCallback / ContextSnapshotCallback

[POS]
`infra/schemas/` 的依赖反转回调协议。
"""

from __future__ import annotations

from collections.abc import Coroutine
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

# Minimum compression savings threshold (Prompt Cache protection).
# See CONTEXT_ENGINEERING.md §5.2.
# Assumes T_prefix=30k, T_cleared > T_prefix * (1-P), at 90% discount: 30k * 0.1 = 3k.
# 3000 tokens balances cache protection without being overly conservative.

from .offload import ContextOffloadResult, EvictedToolCall
from .summary import StructuredSummary


class SummaryPersistCallback(Protocol):
    """Summary persistence callback protocol (dependency inversion).

    Framework layer defines this protocol; business layer injects the implementation.
    After SummarizeProcessor produces a summary, ContextPipelineMiddleware invokes
    this callback to hand the result to the business layer for persistence.

    Typical business implementation: write summary to Chat.compacted_summary and
    before_message_id to Chat.compacted_before_id.
    """

    def __call__(
        self,
        chat_id: str,
        summary: StructuredSummary,
        before_message_id: str,
        tokens_saved: int,
    ) -> Coroutine[object, object, None]: ...

class ContextCompressOffloadCallback(Protocol):
    """Full tool result offload callback (dependency inversion).

    Called before compression or cache-TTL pruning converts a ToolMessage into a
    compact/restorable reference. The scope is a framework-neutral isolation key;
    business identity such as user/account IDs must stay outside this callback.
    On error or empty return, callers must degrade without irreversible data loss.
    """

    def __call__(
        self, *, content: str, tool_name: str, scope_id: str | None
    ) -> Coroutine[object, object, str | ContextOffloadResult]: ...

class ContextCompressEvictionCallback(Protocol):
    """Compression eviction callback protocol (dependency inversion).

    Triggered when tool calls are truncated/compressed (evicted from full context).
    Can be used to implement Zero-cost Memory Extraction Boundary and similar logic.
    """

    def __call__(
        self, evicted_pairs: list[EvictedToolCall], user_goal_hint: str
    ) -> Coroutine[object, object, None]: ...

class ContextSnapshotCallback(Protocol):
    """Pre-compression full message snapshot callback (dependency inversion).

    Called before compression triggers, serializing complete messages to a sanitized+gzipped
    JSONL snapshot file. Symmetric design with ContextCompressOffloadCallback: framework
    defines protocol, business layer injects implementation.
    On error or empty return, compression continues (degrades to no-snapshot mode).

    Returns:
        Workspace-relative path to the snapshot file, or empty string on failure.
    """

    def __call__(
        self, *, messages: list[BaseMessage], chat_id: str | None, user_id: str | None
    ) -> Coroutine[object, object, str]: ...
