"""Smart cron job name generation with semantic-aware truncation.

[INPUT]
- prompt: str | command: str (POS: User's original task description)
- max_length: int (POS: Maximum name length, default 30)
- cron.types::is_system_job_name (POS: cron data models)

[OUTPUT]
- generate_job_name: Truncated name with "..." suffix preserving semantic integrity

[POS]
Intelligently truncates long prompts/commands while preserving readability.
Prioritizes breaking at punctuation marks or spaces to maintain semantic coherence.
Handles both English (word-boundary) and Chinese (character-boundary) text.
A generated name never starts with the reserved prefix, which the manager refuses to every job a user creates.
"""

from __future__ import annotations

import re

from myrm_agent_harness.toolkits.cron.types import is_system_job_name

_LEADING_UNDERSCORES_AND_SPACE = re.compile(r"^[_\s]+")


def generate_job_name(text: str, max_length: int = 30) -> str:
    """Generate a smart-truncated job name from prompt or command.

    Algorithm:
    1. Try to break at Chinese/English punctuation within max_length
    2. Fall back to space-boundary for English
    3. Final fallback: character-boundary with "..." suffix

    A text that starts with the reserved prefix (``__main__.py ...``) loses its leading underscores and spaces first.

    Args:
        text: Source text (prompt or command)
        max_length: Max length before adding "..." (default 30)

    Returns:
        Truncated name, max length = max_length + 3 (for "...")
    """
    text = text.strip()
    if is_system_job_name(text):
        text = _LEADING_UNDERSCORES_AND_SPACE.sub("", text)

    if not text:
        return "Unnamed Task"

    # No truncation needed
    if len(text) <= max_length:
        return text

    # Punctuation marks to break at (ordered by preference)
    punctuation_marks = ["。", "！", "？", "；", "，", ".", "!", "?", ";", ","]

    # Try to break at punctuation within max_length
    for i in range(max_length - 1, max(0, max_length - 15), -1):
        if text[i] in punctuation_marks:
            return text[: i + 1] + "..."

    # Try to break at space (for English)
    for i in range(max_length - 1, max(0, max_length - 15), -1):
        if text[i] == " ":
            return text[:i] + "..."

    # Final fallback: hard truncate at character boundary
    return text[:max_length] + "..."


__all__ = ["generate_job_name"]
