"""Compaction result types.

[INPUT]
(none — stdlib only)

[OUTPUT]
- CompactReason: Closed set of reasons ``compact_chat`` gives for a compaction that did not happen
- CompactResult: Immutable dataclass for compaction attempt outcome

[POS]
Compaction 结果值对象。被 compact_service.py facade 与 service.py 引用；渠道桥接与 Web 端按 CompactReason 的取值归类呈现。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CompactReason(StrEnum):
    """Why ``compact_chat`` did not compact.

    The values reach end users' screens through the compact API and the IM bridge, so they are bare codes: counts and
    exception text go to the log, never into a reason.
    """

    CONCURRENT_COMPACTION = "concurrent_compaction_in_progress"
    SUMMARIZE_CIRCUIT_OPEN = "summarize_circuit_open"
    CHAT_NOT_FOUND = "chat_not_found"
    NO_COMPACTABLE_MESSAGES = "no_compactable_messages"
    TOO_FEW_MESSAGES = "too_few_messages"
    ANTI_THRASH_ACTIVE = "compression_anti_thrash_active"
    TIMEOUT = "timeout"
    PERSIST_FAILED = "persist_failed"


@dataclass(frozen=True, slots=True)
class CompactResult:
    """Outcome of a compaction attempt.

    ``reason`` is a ``CompactReason`` value when ``compact_chat`` declined or failed. The idle gate, which decides
    before it calls ``compact_chat``, stores its own free-text decisions there; only its log and the pre-reply SSE
    phase lookup read them.
    ``original_tokens`` counts what the compaction replaced: the stored summary plus the messages after it.
    """

    compacted: bool
    original_tokens: int = 0
    summary_tokens: int = 0
    tokens_saved: int = 0
    message_count: int = 0
    backup_path: str | None = None
    reason: str | None = None
    attempted: bool = False
