"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- FeedbackSignal: Detected feedback polarity from user messages.
- detect_feedback_signals: Detect user feedback signals from recent conversation turns.
- detect_correction_signals: Detect explicit user correction signals in recent conversation turns.

[POS]
记忆提取子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from enum import StrEnum

logger = logging.getLogger(__name__)


class FeedbackSignal(StrEnum):
    """Detected feedback polarity from user messages."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NONE = "none"


_NEGATIVE_PATTERNS = (
    re.compile(
        r"\bthat(?:'s| is) (?:wrong|incorrect|not (?:right|what I))\b", re.IGNORECASE
    ),
    re.compile(r"\byou (?:misunderstood|got it wrong|made a mistake)\b", re.IGNORECASE),
    re.compile(r"\bno[,.]?\s+I (?:meant|said|asked|want)\b", re.IGNORECASE),
    re.compile(
        r"\bactually[,.]?\s+(?:it should|you should|the correct)\b", re.IGNORECASE
    ),
    re.compile(r"\b(?:please\s+)?(?:redo|try again)\b", re.IGNORECASE),
    re.compile(r"\bshould be\b.+\bnot\b", re.IGNORECASE),
    re.compile(
        r"\bthat(?:'s| is) (?:not what I|not correct|not accurate)\b", re.IGNORECASE
    ),
    re.compile(r"不对"),
    re.compile(r"你(?:理解|搞|弄)错了"),
    re.compile(r"你理解有误"),
    re.compile(r"重新(?:来|做|试)"),
    re.compile(r"换一种"),
    re.compile(r"不是这样"),
    re.compile(r"错了"),
    re.compile(r"不是我(?:要|想要)的"),
    re.compile(r"记错了"),
)

_POSITIVE_PATTERNS = (
    re.compile(
        r"\b(?:that(?:'s| is) (?:exactly|perfectly|absolutely) (?:right|correct|what I))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:perfect|excellent|awesome|great job|well done|spot on|nailed it)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bthat(?:'s| is) (?:right|correct)\b", re.IGNORECASE),
    re.compile(r"\bthank(?:s| you)\s+(?:so much|a lot|very much)\b", re.IGNORECASE),
    re.compile(r"\byou remembered\b", re.IGNORECASE),
    re.compile(r"\byou (?:got|nailed) it\b", re.IGNORECASE),
    re.compile(r"太[好棒]了"),
    re.compile(r"非常[好棒]"),
    re.compile(r"完全正确"),
    re.compile(r"就是(?:这个|这样|我要的)"),
    re.compile(r"(?:没错|对的|正确)"),
    re.compile(r"记得(?:很)?准"),
    re.compile(r"你记(?:住|得)了"),
)

_FEEDBACK_SCAN_WINDOW = 6


def detect_feedback_signals(messages: Sequence[dict[str, str]]) -> FeedbackSignal:
    """Detect user feedback signals from recent conversation turns.

    Scans the last few user messages for positive/negative feedback patterns
    (Chinese + English). Negative takes priority over positive across all
    scanned messages — if any message contains a negative signal, NEGATIVE
    is returned regardless of positive signals in other messages.
    """
    recent = messages[-_FEEDBACK_SCAN_WINDOW:]
    found_positive = False
    for msg in recent:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "").strip()
        if not content:
            continue
        if any(p.search(content) for p in _NEGATIVE_PATTERNS):
            return FeedbackSignal.NEGATIVE
        if not found_positive and any(p.search(content) for p in _POSITIVE_PATTERNS):
            found_positive = True
    return FeedbackSignal.POSITIVE if found_positive else FeedbackSignal.NONE


def detect_correction_signals(messages: Sequence[dict[str, str]]) -> bool:
    """Detect explicit user correction signals in recent conversation turns.

    Convenience wrapper: returns True when negative feedback is detected.
    """
    return detect_feedback_signals(messages) == FeedbackSignal.NEGATIVE
