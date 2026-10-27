"""Reaction emoji short names for providers whose reaction API rejects a raw unicode glyph.

[INPUT]
- (none)

[OUTPUT]
- to_shortname: a unicode emoji or ``:name:`` -> the short name Slack and Mattermost accept

[POS]
Slack ``reactions.add`` and Mattermost ``/reactions`` only take a short name (a glyph is answered with ``invalid_name`` /
404), while the router's ``ReactionPolicy`` and Telegram, Discord and Matrix speak unicode. The table holds the glyphs a
status reaction realistically uses, with the names both platforms share; anything else passes through unchanged, so a
short name typed into the reaction settings keeps working.
"""

from __future__ import annotations

_SHORTNAME_BY_GLYPH: dict[str, str] = {
    "\U0001f440": "eyes",
    "\u2705": "white_check_mark",
    "\u274c": "x",
    "\U0001f914": "thinking_face",
    "\u26a1": "zap",
    "\U0001f680": "rocket",
    "\U0001f525": "fire",
    "\U0001f44d": "thumbsup",
    "\U0001f44e": "thumbsdown",
    "\U0001f389": "tada",
    "\u2764": "heart",
    "\U0001f64f": "pray",
    "\U0001f4af": "100",
    "\u26a0": "warning",
    "\U0001f9e0": "brain",
    "\U0001f4bb": "computer",
}

# U+FE0E / U+FE0F pick the text or emoji presentation of a glyph; they must not keep it from matching its base glyph.
_DROP_VARIATION_SELECTORS = str.maketrans("", "", "\ufe0e\ufe0f")


def to_shortname(emoji: str) -> str:
    """Short name of ``emoji``; a ``:name:`` is unwrapped and an unknown value is returned unchanged."""
    bare = emoji.strip().strip(":")
    return _SHORTNAME_BY_GLYPH.get(bare.translate(_DROP_VARIATION_SELECTORS), bare)
