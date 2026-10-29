"""Defuse mention-everyone markup in text bound for a Google Chat space.

[INPUT]
- (none)

[OUTPUT]
- defuse_all_mention: Break ``<users/all>`` and ``<chat-user data-user="users/all">`` so they render as literal text.

[POS]
Last step before message text leaves the API client, so agent-written text cannot notify a whole space.
"""

from __future__ import annotations

import re

_ZWSP = "\u200b"
# ``all`` must end at a word boundary so ``<users/allen>`` and ``<users/all_hands>`` are left alone.
_ALL_MENTION = re.compile(
    r"<(?=users/all\b|chat-user\b[^<>]*\bdata-user\s*=\s*[\"']?users/all\b)",
    re.IGNORECASE,
)


def defuse_all_mention(text: str) -> str:
    """Return *text* with every mention-everyone tag broken by a zero-width space after ``<``."""
    return _ALL_MENTION.sub("<" + _ZWSP, text)
