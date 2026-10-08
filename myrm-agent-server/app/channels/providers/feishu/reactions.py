"""Feishu reaction emoji vocabulary shared by the inbound and outbound paths.

[INPUT]
- (none)

[OUTPUT]
- UNICODE_TO_FEISHU_EMOJI: outbound unicode emoji → Feishu ``emoji_type``
- FEISHU_EMOJI_TO_UNICODE: inbound Feishu ``emoji_type`` → unicode emoji

[POS]
Static vocabulary for Feishu message reactions. Keeps the inbound mixin and the outbound mixin
free of each other's imports.
"""

from __future__ import annotations

UNICODE_TO_FEISHU_EMOJI: dict[str, str] = {
    "\u2705": "DONE",
    "\U0001f44c": "OK",
    "\U0001f44d": "THUMBSUP",
    "\u2764\ufe0f": "HEART",
    "\U0001f389": "JIAYI",
    "\U0001f440": "EYES",
}
# Inbound coverage extends beyond the outbound vocabulary because reaction
# events arrive with the platform's full emoji_type set; aligning with
# ``parse_approval_command``'s three tiers (allow_once / allow_always / deny)
# avoids silent drops when an IM user reacts with the documented vocabulary.
FEISHU_EMOJI_TO_UNICODE: dict[str, str] = {
    **{v: k for k, v in UNICODE_TO_FEISHU_EMOJI.items()},
    "THUMBSDOWN": "\U0001f44e",
    "NO": "\u274c",
    "INFINITY": "\u267e",
    "STAR": "\u2b50",
}
