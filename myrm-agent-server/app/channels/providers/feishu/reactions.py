"""Feishu reaction emoji vocabulary shared by the inbound and outbound paths.

[INPUT]
- (none)

[OUTPUT]
- UNICODE_TO_FEISHU_EMOJI: outbound unicode emoji → Feishu ``emoji_type``
- FEISHU_EMOJI_TO_UNICODE: inbound Feishu ``emoji_type`` → unicode emoji

[POS]
Static vocabulary for Feishu message reactions. Keeps the inbound mixin and the outbound mixin
free of each other's imports. Feishu rejects an ``emoji_type`` outside its official list (error
231001) and the names are case-sensitive, so every value here is a spelling taken from that list.
"""

from __future__ import annotations

UNICODE_TO_FEISHU_EMOJI: dict[str, str] = {
    "\u2705": "DONE",
    "\U0001f44c": "OK",
    "\U0001f44d": "THUMBSUP",
    "\u2764\ufe0f": "HEART",
    "\U0001f389": "JIAYI",
    "\U0001f440": "Typing",
    "\U0001f914": "THINKING",
    "\U0001f4af": "Hundred",
    "\u274c": "CrossMark",
    "\U0001f44e": "ThumbsDown",
    "\U0001f494": "HEARTBROKEN",
    "\U0001f635": "DIZZY",
}
# Reaction events carry the platform's full emoji_type set. Approval by reaction reads the
# allow_once / allow_always / deny alphabet of ``parse_approval_command``; Feishu has no type for
# the allow_always glyphs (♾️ ⭐), so that tier is only reachable through the text aliases.
FEISHU_EMOJI_TO_UNICODE: dict[str, str] = {
    **{v: k for k, v in UNICODE_TO_FEISHU_EMOJI.items()},
    "MUSCLE": "\U0001f4aa",
}
