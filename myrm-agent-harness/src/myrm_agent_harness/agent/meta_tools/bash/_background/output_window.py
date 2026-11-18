"""The window of one stream that a read of a background job's output shows: capped to a size budget, then masked.

[INPUT]
- agent.security.redact::redact_sensitive_text (POS: facade of the redaction domain)

[OUTPUT]
- WINDOW_MAX_CHARS: the most characters of one stream a single read shows
- cap_window: the newest lines of a window that fit the budget, and whether older ones were cut
- redact_window: the window with secrets masked, line by line and across lines

[POS]
Egress half of the output chain. The ring and the log keep the text as the program printed it; every read passes the window through here, so a secret is masked once per read instead of once per line printed, and a key block that spans lines is seen whole.
"""

from __future__ import annotations

from collections.abc import Sequence

from myrm_agent_harness.agent.security.redact import redact_sensitive_text

# Masking cost grows with the text it scans, and a window of key-block openers that never close is the worst case:
# a read looks at a bounded window, and what lies beyond it is in the log.
WINDOW_MAX_CHARS = 64 * 1024


def cap_window(lines: Sequence[str]) -> tuple[list[str], bool]:
    """The newest lines whose total size fits ``WINDOW_MAX_CHARS``, and whether older lines were left out.

    The newest line is always kept, however long.
    """
    kept = 0
    used = 0
    for line in reversed(lines):
        used += len(line) + 1
        if kept and used > WINDOW_MAX_CHARS:
            break
        kept += 1
    return list(lines[len(lines) - kept :]), kept < len(lines)


def redact_window(lines: Sequence[str]) -> list[str]:
    """Mask the secrets in a window: each line on its own, then the lines as one text.

    The two passes find different things. A form body (``password=x&lang=en``) is masked only inside a single line;
    a private-key block or a JSON pair split over two lines only in the joined text.
    """
    if not lines:
        return []
    per_line = [redact_sensitive_text(line) for line in lines]
    return redact_sensitive_text("\n".join(per_line)).split("\n")


__all__ = ["WINDOW_MAX_CHARS", "cap_window", "redact_window"]
