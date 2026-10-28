"""``to_shortname`` gives Slack and Mattermost the short name their reaction APIs require instead of a raw glyph."""

from __future__ import annotations

import re

import pytest

from app.channels.providers import _emoji_shortnames
from app.channels.providers._emoji_shortnames import to_shortname
from app.channels.routing.router_models import ReactionPolicy

# Mattermost's server-side validation of ``emoji_name`` (model/reaction.go); Slack's names fit it as well.
_VALID_NAME = re.compile(r"^[a-zA-Z0-9\-\+_]+$")


@pytest.mark.parametrize(
    ("emoji", "name"),
    [
        (ReactionPolicy().processing_emoji, "eyes"),
        (ReactionPolicy().completion_emoji, "white_check_mark"),
        (ReactionPolicy().failure_emoji, "x"),
    ],
)
def test_the_routers_default_reactions_have_a_short_name(emoji: str, name: str) -> None:
    assert to_shortname(emoji) == name


# The glyphs the reaction settings page offers (ChannelsSection.tsx) plus the funnel's last failure fallback.
@pytest.mark.parametrize(
    ("emoji", "name"),
    [
        pytest.param("\u23f3", "hourglass_flowing_sand", id="hourglass"),
        pytest.param("\U0001f4ad", "thought_balloon", id="thought-balloon"),
        pytest.param("\u2728", "sparkles", id="sparkles"),
        pytest.param("\U0001f64c", "raised_hands", id="raised-hands"),
        pytest.param("\U0001f494", "broken_heart", id="broken-heart"),
        pytest.param("\U0001f6ab", "no_entry_sign", id="no-entry-sign"),
        pytest.param("\u26d4", "no_entry", id="no-entry"),
        pytest.param("\U0001f635", "dizzy_face", id="dizzy-face"),
        pytest.param("\U0001f622", "cry", id="crying-face"),
    ],
)
def test_every_glyph_the_settings_page_offers_has_a_short_name(emoji: str, name: str) -> None:
    assert to_shortname(emoji) == name


@pytest.mark.parametrize(
    ("emoji", "name"),
    [
        (":eyes:", "eyes"),
        ("  :thumbsup: ", "thumbsup"),
        ("\u2764\ufe0f", "heart"),
        ("\u26a0\ufe0f", "warning"),
        ("\u26a1\ufe0e", "zap"),
    ],
)
def test_colons_whitespace_and_variation_selectors_do_not_hide_the_name(emoji: str, name: str) -> None:
    assert to_shortname(emoji) == name


@pytest.mark.parametrize("emoji", ["wave", "\U0001f9ff", "\U0001f44d\U0001f3fd"])
def test_an_unknown_value_passes_through_unchanged(emoji: str) -> None:
    assert to_shortname(emoji) == emoji


def test_a_value_that_is_only_colons_becomes_empty() -> None:
    assert to_shortname(" : ") == ""


def test_every_mapped_name_is_one_the_platforms_accept() -> None:
    names = _emoji_shortnames._SHORTNAME_BY_GLYPH.values()

    assert all(_VALID_NAME.match(name) for name in names)
    assert len(set(names)) == len(names)
