"""The contrast helper reads colours the way a browser cascades them, and fails loudly instead of passing on what it cannot read."""

from __future__ import annotations

import pytest

from tests.support.wcag_contrast import (
    MIN_TEXT_CONTRAST,
    SINGLE_PALETTE,
    assert_readable,
    assert_single_palette,
    assert_visible,
    contrast,
    custom_properties,
    declared,
    declared_value,
    effective,
    resolve_variables,
    single_hex,
    split_themes,
    stylesheet,
)

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


def test_a_colour_inside_a_shorthand_is_read() -> None:
    css = "input{border:1px solid #6B7280;box-shadow:0 0 0 2px #636}"

    assert declared(css, "input", "border") == "#6b7280"
    assert declared(css, "input", "box-shadow") == "#663366"


@pytest.mark.parametrize(
    ("rule", "prop"),
    [
        ("p{color:rgb(1,2,3)}", "color"),
        ("p{color:red}", "color"),
        ("p{color:var(--ink)}", "color"),
        ("p{border:none}", "border"),
        ("p{box-shadow:0 0 0 2px #111,0 0 0 4px #222}", "box-shadow"),
    ],
    ids=["rgb", "named", "variable", "no-colour", "two-colours"],
)
def test_a_declaration_that_does_not_hold_exactly_one_hex_colour_is_an_error(rule: str, prop: str) -> None:
    with pytest.raises(AssertionError, match="hex colour"):
        declared(rule, "p", prop)


def test_a_dark_rule_in_another_notation_cannot_fall_back_to_the_light_colour() -> None:
    light, dark = split_themes("p{color:#111}\n@media(prefers-color-scheme:dark){p{color:rgb(240,240,240)}}")

    assert effective(light, dark, "light", "p", "color") == "#111111"
    with pytest.raises(AssertionError, match="hex colour"):
        effective(light, dark, "dark", "p", "color")


def test_alternative_spellings_of_one_property_are_tried_in_order() -> None:
    light, dark = split_themes("input{border:1px solid #111}\n@media(prefers-color-scheme:dark){input{border-color:#eee}}")
    spellings = ("border-color", "border")

    assert effective(light, dark, "light", "input", *spellings) == "#111111"
    assert effective(light, dark, "dark", "input", *spellings) == "#eeeeee"


_THREE_TO_ONE = "<style>p{color:#949494}\nq{color:#959595}\n.card{background:#fff}</style>"


def test_a_mark_needs_three_to_one_and_text_needs_four_and_a_half() -> None:
    assert_visible(_THREE_TO_ONE, "light", "p", ("color",), ".card")
    with pytest.raises(AssertionError, match=r"is 2\.995:1"):
        assert_visible(_THREE_TO_ONE, "light", "q", ("color",), ".card")
    with pytest.raises(AssertionError, match=r"is 3\.033:1"):
        assert_readable(_THREE_TO_ONE, "light", "p", ".card")


_PRETTY = """\
.card {
  background: #20202b;
  border: 1px solid #6b7280;
}
    button {
      color: #fff;
      background: #0369a1;
    }
button:hover { background: #075985; }
.page button { color: #123456; }
h1 { font-size: 1rem; color: #fff; }
"""


def test_a_pretty_printed_stylesheet_reads_like_a_minified_one() -> None:
    assert declared(_PRETTY, ".card", "background") == "#20202b"
    assert declared(_PRETTY, ".card", "border") == "#6b7280"
    assert declared(_PRETTY, "button", "color") == "#ffffff"
    assert declared(_PRETTY, "button:hover", "background") == "#075985"
    assert declared(_PRETTY, "h1", "color") == "#ffffff"


def test_indentation_does_not_let_a_selector_match_a_longer_or_deeper_rule() -> None:
    assert declared(_PRETTY, "button", "background") == "#0369a1"
    assert declared("  button:hover { background: #075985; }", "button", "background") is None
    assert declared("  .page button { color: #123456; }", "button", "color") is None
    assert declared("  .card-title { color: #123456; }", ".card", "color") is None
    assert declared("button { border-color: #123456; }", "button", "border") is None


def test_a_pretty_printed_rule_is_read_in_the_last_rule_wins_order() -> None:
    css = "button {\n  color: #111;\n}\n  button {\n  color: #222;\n}\n"

    assert declared(css, "button", "color") == "#222222"


def test_a_pretty_printed_page_is_checked_against_the_bar() -> None:
    page = "<style>\n  .card {\n    background: #ffffff;\n  }\n  p {\n    color: #767676;\n  }\n  q { color: #777777; }\n</style>"

    assert_readable(page, "light", "p", ".card")
    with pytest.raises(AssertionError, match=r"is 4\.4\d\d:1"):
        assert_readable(page, "light", "q", ".card")


def test_a_declared_value_is_the_text_of_the_last_matching_rule_not_only_a_colour() -> None:
    css = "input:focus{outline:2px solid transparent;opacity:1}\ninput:focus {\n  outline: 1px dotted #fff;\n}\n"

    assert declared_value(css, "input:focus", "outline") == "1px dotted #fff"
    assert declared_value(css, "input:focus", "opacity") == "1"
    assert declared_value(css, "input:focus", "color") is None
    assert declared_value(css, "input", "outline") is None


def test_a_page_with_one_palette_is_read_as_the_single_palette() -> None:
    page = "<style>p{color:#111}</style>"
    light, dark = split_themes(stylesheet(page))

    assert effective(light, dark, SINGLE_PALETTE, "p", "color") == "#111111"
    assert_single_palette(page)


@pytest.mark.parametrize(
    "block",
    ["@media(prefers-color-scheme:dark){p{color:#eee}}", "@media (prefers-color-scheme: dark) { p { color: #eee } }"],
    ids=["minified", "spaced"],
)
def test_a_second_palette_is_an_error(block: str) -> None:
    with pytest.raises(AssertionError, match="prefers-color-scheme"):
        assert_single_palette(f"<style>p{{color:#111}}{block}</style>")


_ATTRIBUTE_PAGE = """\
:root {
  --bg: #ffffff;
  --ink: #111111;
}
[data-theme="dark"] {
  --bg: #000000;
}
body { background: var(--bg); color: var(--ink); }
.card { background: var(--ink); color: var(--bg); }
"""


def test_a_page_themed_by_custom_properties_is_read_with_each_themes_values() -> None:
    light, dark = split_themes(_ATTRIBUTE_PAGE)

    assert effective(light, dark, "light", "body", "background") == "#ffffff"
    assert effective(light, dark, "dark", "body", "background") == "#000000"
    assert effective(light, dark, "dark", "body", "color") == "#111111"
    assert effective(light, dark, "dark", ".card", "color") == "#000000"


def test_a_page_themed_by_custom_properties_is_checked_against_the_bar() -> None:
    page = f"<style>{_ATTRIBUTE_PAGE}</style>"

    assert_readable(page, "light", "body", "body")
    with pytest.raises(AssertionError, match=r"body color on body in dark: #111111 on #000000 is 1\.1\d\d:1"):
        assert_readable(page, "dark", "body", "body")


@pytest.mark.parametrize(
    "extra",
    ['[data-theme="dark"] .card { color: #fff; }', '[data-theme="dark"] { --ink: #eee; }'],
    ids=["descendant-rule", "second-block"],
)
def test_a_dark_attribute_rule_other_than_the_one_block_of_properties_is_an_error(extra: str) -> None:
    with pytest.raises(AssertionError, match="one block of custom properties"):
        split_themes(_ATTRIBUTE_PAGE + extra)


def test_a_dark_attribute_block_without_properties_is_an_error() -> None:
    with pytest.raises(AssertionError, match="one block of custom properties"):
        split_themes('body{color:#111}\n[data-theme="dark"]{color:#eee}')


def test_a_page_themed_two_ways_is_an_error() -> None:
    with pytest.raises(AssertionError, match="use one"):
        split_themes(_ATTRIBUTE_PAGE + "@media(prefers-color-scheme:dark){body{color:#eee}}")


def test_a_variable_no_rule_declares_is_an_error() -> None:
    with pytest.raises(AssertionError, match=r"var\(--ghost\) is used"):
        split_themes(_ATTRIBUTE_PAGE + "p { color: var(--ghost); }")


def test_custom_properties_are_the_declarations_of_the_exact_selector() -> None:
    assert custom_properties(_ATTRIBUTE_PAGE, ":root") == {"--bg": "#ffffff", "--ink": "#111111"}
    assert custom_properties(_ATTRIBUTE_PAGE, '[data-theme="dark"]') == {"--bg": "#000000"}
    assert custom_properties(_ATTRIBUTE_PAGE, "body") == {}
    assert custom_properties(":root{--a:#111;--a:#222}", ":root") == {"--a": "#222"}


def test_variables_are_replaced_wherever_they_sit_in_a_value() -> None:
    assert resolve_variables("border: 1px solid var(--edge)", {"--edge": "#abc"}) == "border: 1px solid #abc"


def test_a_single_hex_names_where_it_was_read_when_it_finds_none_or_many() -> None:
    assert single_hex("1px solid #ABC", "p gives border") == "#aabbcc"
    with pytest.raises(AssertionError, match=r"p gives border 'none', which is not exactly one hex colour"):
        single_hex("none", "p gives border")
