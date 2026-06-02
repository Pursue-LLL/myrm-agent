"""Smart message splitting — preserves code block integrity.

Splits long messages at natural boundaries while ensuring code fences
are properly closed and reopened across chunk boundaries.

[INPUT]
(No external dependencies, pure string processing)

[OUTPUT]
- split_message(): str → list[str]（Message chunk list split at natural boundaries）

[POS]
Smart long-message splitter. Line-by-line processing with fence state machine,
auto-closing and reopening code blocks that span chunks. "escape" fence protection
2. Enhanced: Supports both ``` and ~~~ fences (3-10 symbols)
3. Smart: Intelligent line splitting at whitespace/punctuation boundaries
4. Configurable: Overflow tolerance for semantic preservation
"""

from __future__ import annotations

import re

# Matches code fences: ``` or ~~~, 3-10 symbols, optional language tag
_CODE_FENCE = re.compile(r"^(?P<fence>[`~]{3,10})(?P<lang>\w*)\s*$")


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


def _smart_split_line(line: str, max_len: int) -> list[str]:
    """Intelligently split a long line, preferring whitespace/punctuation boundaries.

    Args:
        line: The line to split
        max_len: Maximum segment length

    Returns:
        List of line segments, each <= max_len (except edge cases where no split point found)

    Strategy:
        1. Try to split at whitespace or punctuation within 10% tolerance of max_len
        2. Fallback to hard-split if no good boundary found
    """
    if len(line) <= max_len:
        return [line]

    segments = []
    current_pos = 0

    while current_pos < len(line):
        end_pos = min(current_pos + max_len, len(line))

        if end_pos < len(line):
            # Not the last segment, search for best split point
            # Look backwards from end_pos within 10% range
            search_start = max(current_pos + 1, int(end_pos * 0.9))
            best_split = end_pos

            # Prefer splitting at whitespace or punctuation
            for i in range(end_pos - 1, search_start - 1, -1):
                if line[i] in " \t,.;:!?|&)]}":
                    best_split = i + 1
                    break

            segments.append(line[current_pos:best_split])
            current_pos = best_split
        else:
            # Last segment
            segments.append(line[current_pos:end_pos])
            break

    return segments


def split_message(
    content: str, max_len: int = 4096, overflow_tolerance: float = 0.2, fence_patterns: re.Pattern | None = None
) -> list[str]:
    """Split content into chunks with perfect fence-aware semantic preservation.

    Features:
        1. Fence state tracking: ``` and ~~~ (3-10 symbols) support
        2. Bug fix: Long lines inside fences won't escape fence protection
        3. Smart splitting: Prefers whitespace/punctuation boundaries
        4. Configurable overflow tolerance for semantic integrity

    Priority order:
        1. Line boundary with fence integrity
        2. Smart split at whitespace/punctuation
        3. Hard split for extreme cases (with fence wrapper if inside fence)

    Args:
        content: Text to split
        max_len: Maximum chunk length (soft limit, can be exceeded for fence integrity)
        overflow_tolerance: Allowed overflow ratio for semantic preservation (default 0.2 = 20%)
        fence_patterns: Optional custom fence regex pattern (default: ``` or ~~~, 3-10 symbols)

    Returns:
        List of chunks, each properly fence-wrapped if needed

    Examples:
        >>> # Discord with strict limit
        >>> split_message(text, max_len=2000, overflow_tolerance=0.15)

        >>> # Slack with more flexibility
        >>> split_message(text, max_len=4000, overflow_tolerance=0.3)
    """
    if len(content) <= max_len:
        return [content]

    # Use custom pattern or default
    fence_pattern = fence_patterns or _CODE_FENCE

    # Reserve space for closing fence
    fence_close_len = 4  # "\n```" or "\n~~~"

    # Helper function with custom pattern support
    def _detect_fence_local(line: str) -> tuple[bool, str]:
        """Local fence detection using configurable pattern."""
        match = fence_pattern.match(line.strip())
        if match:
            return True, match.group(0)
        return False, ""

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    fence_open = ""  # Tracks the opening fence marker (e.g., "```python")

    def _get_fence_symbol(fence_marker: str) -> str:
        """Extract fence symbol from marker (e.g., "```python" -> "```")."""
        match = re.match(r"^[`~]+", fence_marker)
        return match.group(0) if match else "```"

    def _flush(fence_state_to_use: str = "") -> None:
        """Flush current buffer to chunks, closing fence if needed.

        Args:
            fence_state_to_use: Fence state to use for closing (defaults to current fence_open)
        """
        nonlocal fence_open
        if not current:
            return

        # Use provided fence state, or default to current fence_open
        state_to_check = fence_state_to_use if fence_state_to_use is not None else fence_open

        body = "".join(current).rstrip("\n")
        if state_to_check:
            # Close with matching fence symbol
            fence_symbol = _get_fence_symbol(state_to_check)
            body += f"\n{fence_symbol}"
        chunks.append(body)
        current.clear()

    for line in content.split("\n"):
        line_with_nl = line + "\n"
        stripped = line.strip()

        # Detect fence toggle
        is_fence, fence_marker = _detect_fence_local(stripped)

        # Store fence state before this line
        fence_open_before = fence_open

        if is_fence:
            if fence_open:
                # Check if this is the closing fence (same symbol)
                if _get_fence_symbol(fence_marker) == _get_fence_symbol(fence_open):
                    fence_open = ""
            else:
                # Opening fence
                fence_open = fence_marker

        # Check if we need to flush before adding this line
        reserved = fence_close_len if fence_open else 0
        if current and current_len + len(line_with_nl) + reserved > max_len:
            saved_fence = fence_open_before  # Use fence state BEFORE this line
            _flush(fence_state_to_use=saved_fence)  # Flush with correct fence state
            current_len = 0

            if saved_fence:
                # Re-open fence in next chunk
                fence_open = saved_fence
                reopener = saved_fence + "\n"
                current.append(reopener)
                current_len += len(reopener)

        # Handle long lines (THE KEY BUG FIX)
        if len(line_with_nl) > max_len:
            if fence_open:
                # ===== CRITICAL: Preserve fence integrity for long lines =====
                fence_symbol = _get_fence_symbol(fence_open)
                fence_overhead = len(fence_open) + 2 + len(fence_symbol) + 1
                total_len = len(line) + fence_overhead

                # Flush current buffer first (will auto-close fence)
                if current:
                    _flush(fence_state_to_use=fence_open)
                    current_len = 0

                if total_len <= max_len * (1 + overflow_tolerance):
                    # Strategy 1: Keep entire line as single chunk (slight overflow ok)
                    chunks.append(f"{fence_open}\n{line}\n{fence_symbol}")
                else:
                    # Strategy 2: Smart split with fence wrapper for each segment
                    available_len = max_len - fence_overhead
                    segments = _smart_split_line(line, max(available_len, 100))

                    for seg in segments:
                        # Each segment wrapped in fence
                        chunks.append(f"{fence_open}\n{seg}\n{fence_symbol}")

                # After handling long line, re-open fence in current for subsequent lines
                # (fence_open state is unchanged, so fence is still logically open)
                current.append(fence_open + "\n")
                current_len += len(fence_open) + 1
            else:
                # Not in fence: normal hard-split
                for i in range(0, len(line), max_len):
                    chunks.append(line[i : i + max_len])
        else:
            # Normal-length line
            current.append(line_with_nl)
            current_len += len(line_with_nl)

    # Final flush
    if current:
        body = "".join(current).rstrip("\n")
        if fence_open:
            fence_symbol = _get_fence_symbol(fence_open)
            body += f"\n{fence_symbol}"
        chunks.append(body)

    return [c for c in chunks if c.strip()]
