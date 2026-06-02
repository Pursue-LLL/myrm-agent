"""Universal text processing utilities for channel formatting.

[INPUT]

[OUTPUT]
- extract_safe_regions(): Extract pattern matches outside code blocks

[POS]
Universal text utilities. Provides code-block-aware text processing
for all channel implementations (mention extraction, link parsing, etc.).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from re import Match


_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def extract_safe_regions(
    text: str,
    pattern: str | re.Pattern[str],
    *,
    exclude_fenced_code: bool = True,
    exclude_inline_code: bool = True,
) -> list[Match[str]]:
    """Extract pattern matches from text, EXCLUDING code blocks.

    Useful for processing mentions, links, or other patterns while
    preserving code blocks intact (e.g., @user in code should NOT
    trigger mention conversion).

    Args:
        text: Input text to search
        pattern: Regex pattern (str or compiled Pattern)
        exclude_fenced_code: If True, exclude matches inside ```code```
        exclude_inline_code: If True, exclude matches inside `code`

    Returns:
        List of Match objects for matches OUTSIDE code blocks

    Example:
        >>> text = "Hi @alice, check ```@bob in code```"
        >>> matches = extract_safe_regions(text, r"@(\\w+)")
        >>> [m.group() for m in matches]
        ['@alice']  # @bob is excluded (inside code fence)
    """
    if isinstance(pattern, str):
        pattern = re.compile(pattern)

    code_ranges: list[tuple[int, int]] = []

    if exclude_fenced_code:
        code_ranges.extend((m.start(), m.end()) for m in _FENCED_CODE_RE.finditer(text))

    if exclude_inline_code:
        code_ranges.extend((m.start(), m.end()) for m in _INLINE_CODE_RE.finditer(text))

    code_ranges.sort()

    all_matches = list(pattern.finditer(text))

    def _is_inside_code(start: int, end: int) -> bool:
        """Check if range overlaps with any code block."""
        for code_start, code_end in code_ranges:
            if code_start <= start < code_end or code_start < end <= code_end:
                return True
            if start <= code_start < end:
                return True
        return False

    safe_matches = [m for m in all_matches if not _is_inside_code(m.start(), m.end())]

    return safe_matches
