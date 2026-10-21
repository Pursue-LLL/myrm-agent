"""Compaction result types.

[INPUT]
(none — stdlib only)

[OUTPUT]
- CompactResult: Immutable dataclass for compaction attempt outcome

[POS]
Compaction 结果值对象。被 service.py、summarize_guard.py 等引用。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompactResult:
    """Outcome of a compaction attempt."""

    compacted: bool
    original_tokens: int = 0
    summary_tokens: int = 0
    tokens_saved: int = 0
    message_count: int = 0
    backup_path: str | None = None
    reason: str | None = None
    attempted: bool = False
