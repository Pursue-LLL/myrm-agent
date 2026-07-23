"""Numeric limits and intervals shared by AgentRouter routing modules.

[POS]
Constants read by router.py, router_stream, and janitor/dedup logic. Includes silence reassurance
thresholds and outbound silent content detection. Unit tests can import directly.
"""

from __future__ import annotations

import re

_MAX_CONCURRENT_AGENTS = 5
_MIN_PROGRESS_INTERVAL = 2.0
_MIN_STREAM_INTERVAL = 0.5
_DEDUP_TTL = 300.0
_DEDUP_MAX_SIZE = 10_000
_CLEANUP_TTL = 3600.0
_SILENCE_REASSURANCE_THRESHOLD = 120.0
_MAX_REASSURANCE_COUNT = 3
_STUCK_TASK_TIMEOUT = 600.0

_SILENT_MARKER = "[SILENT]"
_FENCE_RE = re.compile(r"^```(?:\w+)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def _is_silent_content(text: str | None) -> bool:
    """Return True when agent output is an intentional silence token.

    Matches exact ``[SILENT]`` (with optional whitespace / markdown fence).
    Substantive replies like ``[SILENT] nothing to report`` pass through.
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    fence_match = _FENCE_RE.match(stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()
    if stripped == _SILENT_MARKER:
        return True
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    return bool(lines) and all(ln == _SILENT_MARKER for ln in lines)
