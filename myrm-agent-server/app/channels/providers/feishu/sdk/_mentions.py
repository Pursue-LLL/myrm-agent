"""Defuse mention-everyone markup in text bound for a Feishu chat.

[INPUT]
- (none)

[OUTPUT]
- defuse_at_all: Break ``<at user_id="all">`` / ``<at id=all>`` markup so it renders as literal text.

[POS]
Last step before message and card content leaves the client, so agent-written text cannot notify a whole group.
"""

from __future__ import annotations

import re

_ZWSP = "\u200b"
# Applied to message ``content`` JSON as well as plain card markdown, so quotes may arrive backslash-escaped and
# whitespace as a ``\n`` / ``\t`` escape. ``all`` must end at a word boundary so ``all_hands`` is left alone.
_SPACE = r"(?:\s|\\[nrt])"
_AT_ALL = re.compile(rf"<(?=at{_SPACE}[^<>]*?id{_SPACE}*={_SPACE}*\\?[\"']?all\b)", re.IGNORECASE)


def defuse_at_all(content: str) -> str:
    """Return *content* with every mention-everyone tag broken by a zero-width space after ``<``."""
    return _AT_ALL.sub("<" + _ZWSP, content)
