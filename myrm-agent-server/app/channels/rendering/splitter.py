"""Smart message splitting — preserves code block integrity.

Splits long messages at natural boundaries while ensuring code fences
are properly closed and reopened across chunk boundaries.

[INPUT]
- channels.types::LengthUnit (POS: the unit a channel's text limit is counted in)

[OUTPUT]
- split_message(): str → list[str]（Message chunk list; join-preserving line iteration; limit counted in characters or UTF-8 bytes）
- cap_stream_preview(): cap streaming placeholder preview to channel max length, in the same unit
- BOUNDARY_CHARS / CJK_BOUNDARY_CHARS: shared smart-split punctuation sets

[POS]
Smart long-message splitter for IM outbound delivery. Line-by-line fence state machine
(auto-close/reopen ``` and ~~~ fences across chunks), a hard per-chunk length limit counted in
characters or UTF-8 bytes, ASCII/CJK punctuation boundaries, and shared boundary-char exports for provider-specific splitters.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from ..types import LengthUnit

# Matches code fences: ``` or ~~~, 3-10 symbols, optional language tag
_CODE_FENCE = re.compile(r"^(?P<fence>[`~]{3,10})(?P<lang>\w*)\s*$")

# Smart-split boundaries: ASCII whitespace/punctuation + CJK full-width punctuation.
ASCII_BOUNDARY_CHARS = " \t,.;:!?|&)]}"
CJK_BOUNDARY_CHARS = "，。！？；：、）】》\"'"
BOUNDARY_CHARS = ASCII_BOUNDARY_CHARS + CJK_BOUNDARY_CHARS


def _detect_fence(line: str) -> tuple[bool, str]:
    """Detect if line is a code fence marker.

    Returns:
        (is_fence, fence_marker) where fence_marker is e.g. "```python" or "~~~~"

    Examples:
        "```python" -> (True, "```python")
        "~~~~" -> (True, "~~~~")
        "normal text" -> (False, "")
    """
    match = _CODE_FENCE.match(line.strip())
    if match:
        return True, match.group(0)
    return False, ""


def _fence_symbol(fence_marker: str) -> str:
    """The run of fence characters of a marker: "```python" -> "```"."""
    match = re.match(r"^[`~]+", fence_marker)
    return match.group(0) if match else "```"


def _close_fence(body: str, fence_marker: str) -> str:
    """``body`` closed with the fence symbol of ``fence_marker``; unchanged when no fence is open."""
    if not fence_marker:
        return body
    if body and not body.endswith("\n"):
        body += "\n"
    return body + _fence_symbol(fence_marker)


def _utf8_len(text: str) -> int:
    """UTF-8 size of ``text``; a lone surrogate counts its three bytes instead of raising."""
    return len(text.encode("utf-8", "surrogatepass"))


def _utf8_cost(char: str) -> int:
    """UTF-8 size of one character, consistent with ``_utf8_len``."""
    code = ord(char)
    if code < 0x80:
        return 1
    if code < 0x800:
        return 2
    return 3 if code < 0x10000 else 4


def _measure(unit: LengthUnit) -> Callable[[str], int]:
    """The size function of a length unit; sizes add up, so a chunk's size is the sum of its lines'."""
    return len if unit == "chars" else _utf8_len


def _fit_end(line: str, start: int, budget: int, unit: LengthUnit) -> int:
    """Index where the run of ``line`` from ``start`` costing at most ``budget`` ends.

    A run is never empty: a character dearer than the budget still goes out alone, so splitting terminates.
    """
    if unit == "chars":
        return max(min(start + budget, len(line)), start + 1)
    used = 0
    for index in range(start, len(line)):
        used += _utf8_cost(line[index])
        if used > budget:
            return max(index, start + 1)
    return len(line)


def _smart_split_line(line: str, max_len: int, unit: LengthUnit = "chars") -> list[str]:
    """Intelligently split a long line, preferring whitespace/punctuation boundaries.

    Args:
        line: The line to split
        max_len: Maximum segment size, counted in ``unit``
        unit: What ``max_len`` counts

    Returns:
        List of line segments, each <= max_len (except a single character dearer than max_len)

    Strategy:
        1. Try to split at whitespace or punctuation within 10% tolerance of max_len
        2. Fallback to hard-split if no good boundary found
    """
    if _measure(unit)(line) <= max_len:
        return [line]

    segments = []
    current_pos = 0

    while current_pos < len(line):
        end_pos = _fit_end(line, current_pos, max_len, unit)

        if end_pos < len(line):
            # Not the last segment, search for best split point
            # Look backwards from end_pos within 10% of the current segment window
            window_len = end_pos - current_pos
            search_start = max(current_pos + 1, end_pos - max(1, int(window_len * 0.1)))
            best_split = end_pos

            # Prefer splitting at whitespace or punctuation (incl. CJK full-width)
            for i in range(end_pos - 1, search_start - 1, -1):
                if line[i] in BOUNDARY_CHARS:
                    best_split = i + 1
                    break

            segments.append(line[current_pos:best_split])
            current_pos = best_split
        else:
            # Last segment
            segments.append(line[current_pos:end_pos])
            break

    return segments


_PREVIEW_TRUNC_SUFFIX = "…"


def cap_stream_preview(text: str, max_len: int, *, suffix: str = _PREVIEW_TRUNC_SUFFIX, unit: LengthUnit = "chars") -> str:
    """Cap streaming placeholder preview text to a channel max length.

    Uses the same smart boundary set as ``split_message`` so preview truncation
    prefers whitespace and CJK punctuation over hard mid-character cuts. ``max_len`` is counted in ``unit``.
    """
    measure = _measure(unit)
    if max_len <= 0 or measure(text) <= max_len:
        return text

    suffix_len = measure(suffix)
    if max_len <= suffix_len:
        return text[: _fit_end(text, 0, max_len, unit)]

    body_budget = max_len - suffix_len
    head = _smart_split_line(text, body_budget, unit)[0]
    return head + suffix


def split_message(content: str, max_len: int = 4096, *, unit: LengthUnit = "chars") -> list[str]:
    """Split content into chunks of at most ``max_len`` (counted in ``unit``), keeping code fences intact.

    A chunk that ends inside a fence closes it and the next chunk reopens it with the same marker. A code line
    too long for a chunk of its own is cut at whitespace or punctuation and every piece is fenced. Splitting never
    creates a chunk that holds only a fence marker. A ``max_len`` below the size of a fence's wrapper (opening
    marker, closing symbol and two newlines) cannot be honoured for the code inside that fence.

    Priority order:
        1. Line boundary with fence integrity
        2. Smart split at whitespace/punctuation
        3. Hard split for lines with no boundary (fence-wrapped when inside a fence)

    Args:
        content: Text to split
        max_len: Maximum chunk size, the platform's message limit
        unit: What ``max_len`` counts: characters, or UTF-8 bytes for a platform that limits bytes

    Returns:
        List of non-empty chunks, each at most ``max_len`` in size and fence-balanced
    """
    measure = _measure(unit)
    if measure(content) <= max_len:
        return [content]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    fence_open = ""  # Marker of the fence the scan is inside, e.g. "```python"
    fence_symbol = ""  # Its run of fence characters, e.g. "```"

    def _flush(fence_state: str) -> None:
        """Emit the buffer closed with the fence still open in it; a trailing opener with no code under it is dropped."""
        nonlocal current_len
        if fence_state and current and current[-1].strip() == fence_state:
            current.pop()
            fence_state = ""
        body = "".join(current)
        current.clear()
        current_len = 0
        if body.strip():
            chunks.append(_close_fence(body, fence_state))

    lines = content.split("\n")
    last_idx = len(lines) - 1
    for idx, line in enumerate(lines):
        line_with_nl = line if idx == last_idx else line + "\n"
        line_cost = measure(line_with_nl)
        fence_before, symbol_before = fence_open, fence_symbol

        is_fence, marker = _detect_fence(line)
        if is_fence:
            if not fence_open:
                fence_open, fence_symbol = marker, _fence_symbol(marker)
            elif _fence_symbol(marker) == fence_symbol:
                fence_open = fence_symbol = ""

        if fence_before and not fence_open:
            # Closing fence: a chunk still holding code takes it; a full one was closed by its flush, which
            # leaves nothing to close here.
            if current:
                if current_len + line_cost <= max_len:
                    current.append(line_with_nl)
                    current_len += line_cost
                else:
                    _flush(fence_before)
            continue

        close_len = len(fence_symbol) + 1 if fence_open else 0  # "\n" and the symbol that close the chunk
        if current and current_len + line_cost + close_len > max_len:
            _flush(fence_before)

        if current:
            current.append(line_with_nl)
            current_len += line_cost
            continue

        # First line of a chunk: a code line continues the fence, so it is preceded by the fence marker.
        reopen_len = measure(fence_before) + 1 if fence_before else 0
        if reopen_len + line_cost + close_len <= max_len:
            if fence_before:
                current.append(fence_before + "\n")
            current.append(line_with_nl)
            current_len = reopen_len + line_cost
        elif fence_before:
            segment_len = max(max_len - measure(fence_before) - len(symbol_before) - 2, 1)
            chunks.extend(
                f"{fence_before}\n{segment}\n{symbol_before}"
                for segment in _smart_split_line(line, segment_len, unit)
                if segment.strip()
            )
        else:
            chunks.extend(segment for segment in _smart_split_line(line, max_len, unit) if segment.strip())

    _flush(fence_open)
    return chunks
