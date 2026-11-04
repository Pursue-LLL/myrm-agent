"""Head+tail truncation window

[INPUT]
- re::re (POS: Regex patterns that detect a diagnostic tail)
- typing::NamedTuple (POS: TruncationWindow return structure)

[OUTPUT]
- TruncationWindow: Slice boundaries kept by head+tail truncation
- truncation_window(): Locate the head and tail slices that fit a character budget
- apply_truncation_window(): Join the kept slices around a marker stating how much of each remains
- has_important_tail(): Detect whether a text tail carries diagnostics, a structural close or a summary

[POS]
Decides where head+tail truncation cuts. ``text_utils.smart_truncate`` composes it into one call; callers that must
know which part of a text is omitted (for example to point at the omitted lines) use the window directly, so the cut
and the pointer cannot disagree.
"""

from __future__ import annotations

import re
from typing import NamedTuple

_TAIL_DIAGNOSTIC_PATTERN = re.compile(
    r"\b(error|exception|traceback|panic|failed|fatal|errno|exit.?code|return.?code)\b",
    re.IGNORECASE,
)
_TAIL_STRUCTURAL_END = re.compile(r"[}\]]\s*$")
_TAIL_SUMMARY_PATTERN = re.compile(
    r"\b(total|summary|result|complete|finished|done|passed|rows)\b",
    re.IGNORECASE,
)
_TAIL_CHECK_CHARS = 2000


class TruncationWindow(NamedTuple):
    """Slices kept by head+tail truncation: ``text[:head_end]`` and ``text[tail_start:]``."""

    head_end: int
    tail_start: int


def has_important_tail(text: str) -> bool:
    """Detect whether text tail contains critical diagnostic information.

    Checks the last ~2000 chars for error patterns, structural closures
    (JSON/array end), and summary lines that should be preserved during
    truncation.
    """
    tail = text[-_TAIL_CHECK_CHARS:]
    return bool(
        _TAIL_DIAGNOSTIC_PATTERN.search(tail)
        or _TAIL_STRUCTURAL_END.search(tail.rstrip())
        or _TAIL_SUMMARY_PATTERN.search(tail)
    )


def truncation_window(
    text: str,
    max_chars: int,
    *,
    tail_ratio: float = 0.3,
    important_tail_ratio: float = 0.6,
) -> TruncationWindow | None:
    """Locate the head and tail slices to keep within ``max_chars`` (marker included).

    Returns ``None`` when ``text`` already fits. When the tail holds diagnostics the budget shifts toward it, and both
    cuts snap to a newline when one lies close enough to avoid splitting a line. The window may overlap
    (``head_end >= tail_start``) when the budget is too small to omit anything useful; callers treat that as "fits".
    """
    if len(text) <= max_chars:
        return None

    total = len(text)
    marker = f"\n\n[Truncated: {total} chars -> first {{head}} + last {{tail}}]\n\n"
    marker_overhead = len(marker) + 20
    budget = max(200, max_chars - marker_overhead)

    ratio = max(tail_ratio, important_tail_ratio) if has_important_tail(text) else tail_ratio
    tail_budget = int(budget * ratio)
    head_budget = budget - tail_budget

    head_end = head_budget
    nl = text.rfind("\n", 0, head_budget)
    if nl > head_budget * 0.8:
        head_end = nl

    tail_start = total - tail_budget
    nl = text.find("\n", tail_start)
    if nl != -1 and nl < tail_start + int(tail_budget * 0.2):
        tail_start = nl + 1

    return TruncationWindow(head_end, tail_start)


def apply_truncation_window(text: str, window: TruncationWindow) -> str:
    """Join the kept head and tail around a marker stating how much of each remains."""
    head_part = text[: window.head_end]
    tail_part = text[window.tail_start :]
    marker = f"\n\n[Truncated: {len(text)} chars -> first {len(head_part)} + last {len(tail_part)}]\n\n"
    return head_part + marker + tail_part
