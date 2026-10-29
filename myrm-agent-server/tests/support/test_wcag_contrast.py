"""The contrast helper reads colours the way a browser cascades them, and fails loudly instead of passing on what it cannot read."""

from __future__ import annotations

import pytest

from tests.support.wcag_contrast import MIN_TEXT_CONTRAST, contrast, declared, effective, split_themes

_PAGE = """\
body{background:#fff;color:#111}
.card{background:#eee}
.msg-body p{color:#222222}
p{color:#333}
@media(prefers-color-scheme:dark){body{background:#000;color:#eee}}
@media(prefers-color-scheme:dark){
p{color:#ddd}
.card{background:#111}
}
"""


def test_a_three_digit_colour_reads_like_its_six_digit_form() -> None:
    assert declared("p{color:#bbb}", "p", "color") == "#bbbbbb"
    assert declared("p{color:#BBBBBB}", "p", "color") == "#bbbbbb"


def test_a_bare_selector_ignores_a_rule_for_the_same_tag_deeper_in_the_tree() -> None:
    light, _ = split_themes(_PAGE)

    assert declared(light, "p", "color") == "#333333"
    assert declared(".msg-body p{color:#222222}", "p", "color") is None


def test_every_dark_block_lands_in_the_dark_half_and_nothing_else_does() -> None:
    light, dark = split_themes(_PAGE)

    assert "prefers-color-scheme" not in light
    assert declared(dark, "body", "background") == "#000000"
    assert declared(dark, "p", "color") == "#dddddd"
    assert declared(dark, ".card", "background") == "#111111"
    assert declared(dark, ".msg-body p", "color") is None


def test_a_dark_rule_overrides_the_light_one_and_a_missing_one_falls_back_to_it() -> None:
    light, dark = split_themes(_PAGE)

    assert effective(light, dark, "light", "p", "color") == "#333333"
    assert effective(light, dark, "dark", "p", "color") == "#dddddd"
    assert effective(light, dark, "dark", ".msg-body p", "color") == "#222222"


def test_a_selector_without_the_property_is_an_error() -> None:
    light, dark = split_themes(_PAGE)

    with pytest.raises(AssertionError, match="declares no color"):
        effective(light, dark, "light", ".card", "color")


@pytest.mark.parametrize(
    "dark_block",
    ["@media (prefers-color-scheme: dark){body{color:#fff}}", "@media(prefers-color-scheme:light){body{color:#000}}"],
    ids=["spaced", "other-scheme"],
)
def test_a_colour_scheme_block_in_a_form_the_helper_cannot_read_is_an_error(dark_block: str) -> None:
    with pytest.raises(AssertionError, match="prefers-color-scheme"):
        split_themes("body{color:#111}\n" + dark_block)


def test_contrast_matches_the_published_wcag_values() -> None:
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#ffffff", "#000000") == pytest.approx(21.0)
    assert contrast("#767676", "#ffffff") >= MIN_TEXT_CONTRAST > contrast("#777777", "#ffffff")
