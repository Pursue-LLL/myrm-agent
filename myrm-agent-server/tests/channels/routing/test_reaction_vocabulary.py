"""What a platform's declared reaction vocabulary accepts: everything when none is declared, else only its own glyphs.

The per-role candidate chains that walk this vocabulary are covered in ``reactions/test_status_reaction.py``.
"""

from __future__ import annotations

from app.channels.types import ChannelCapabilities

HOURGLASS = "\u23f3"
CHECK = "\u2705"
THUMBS_UP = "\U0001f44d"
HEART = "\u2764"
HEART_VS16 = "\u2764\ufe0f"


class TestAcceptsReaction:
    def test_a_channel_without_a_declared_vocabulary_accepts_everything(self) -> None:
        assert ChannelCapabilities(reactions=True).accepts_reaction(HOURGLASS)

    def test_a_declared_vocabulary_is_the_only_thing_accepted(self) -> None:
        caps = ChannelCapabilities(reactions=True, reaction_glyphs=frozenset({THUMBS_UP}))
        assert caps.accepts_reaction(THUMBS_UP)
        assert not caps.accepts_reaction(CHECK)

    def test_variation_selectors_do_not_change_the_glyph(self) -> None:
        caps = ChannelCapabilities(reactions=True, reaction_glyphs=frozenset({HEART}))
        assert caps.accepts_reaction(HEART_VS16)
