"""Closest-line hint for a text that a replacement could not find.

[INPUT]
- (none)

[OUTPUT]
- find_closest_lines: "Did you mean?" hint listing the lines of a file nearest to the text that was not found

[POS]
Failure hint of the text-replacement tools. The model sees where the text it meant sits, with line numbers,
and resends it exactly.
"""

from __future__ import annotations

from difflib import SequenceMatcher

_CLOSEST_MIN_SIMILARITY = 0.3


def find_closest_lines(
    old_str: str,
    content: str,
    *,
    context_lines: int = 2,
    max_results: int = 3,
) -> str:
    """Return "did you mean?" hint with closest matching lines, or empty string."""
    if not old_str or not content:
        return ""
    old_lines = old_str.splitlines()
    content_lines = content.splitlines()
    if not old_lines or not content_lines:
        return ""
    anchor = next((ln.strip() for ln in old_lines if ln.strip()), None)
    if anchor is None:
        return ""

    scored: list[tuple[float, int]] = []
    for i, line in enumerate(content_lines):
        stripped = line.strip()
        if stripped:
            ratio = SequenceMatcher(None, anchor, stripped).ratio()
            if ratio >= _CLOSEST_MIN_SIMILARITY:
                scored.append((ratio, i))
    if not scored:
        return ""
    scored.sort(key=lambda x: -x[0])

    parts: list[str] = []
    seen: set[tuple[int, int]] = set()
    for _, idx in scored[:max_results]:
        start = max(0, idx - context_lines)
        end = min(len(content_lines), idx + len(old_lines) + context_lines)
        if (start, end) in seen:
            continue
        seen.add((start, end))
        parts.append("\n".join(f"{start + j + 1:4d}| {content_lines[start + j]}" for j in range(end - start)))
    return ("\n\nDid you mean one of these sections?\n" + "\n---\n".join(parts)) if parts else ""
