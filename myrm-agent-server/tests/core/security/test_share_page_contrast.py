"""The password-gate and status pages keep their text readable and their field edge and focus visible, in both themes."""

from __future__ import annotations

import re

import pytest

from app.core.security.share.share_password_page import render_password_gate_html
from app.core.security.share.share_status_page import ShareLinkState, render_share_status_html
from tests.support.wcag_contrast import Theme, assert_readable, assert_visible, stylesheet

_THEMES = pytest.mark.parametrize("theme", ["light", "dark"])
_FIELD = "input[type=password]"


@_THEMES
@pytest.mark.parametrize(
    ("text", "surface"),
    [
        ("body", ".card"),
        ("p", ".card"),
        (".err", ".card"),
        ("button", "button"),
        ("button", "button:hover"),
    ],
    ids=["title", "prompt", "error", "button", "button-hover"],
)
def test_password_gate_text_is_readable_on_its_surface(theme: Theme, text: str, surface: str) -> None:
    assert_readable(render_password_gate_html(), theme, text, surface)


@_THEMES
def test_password_gate_placeholder_is_readable_in_the_field(theme: Theme) -> None:
    assert_readable(render_password_gate_html(), theme, f"{_FIELD}::placeholder", _FIELD)


@_THEMES
@pytest.mark.parametrize(
    ("mark", "props", "surface"),
    [
        (_FIELD, ("border-color", "border"), _FIELD),
        (_FIELD, ("border-color", "border"), ".card"),
        (f"{_FIELD}:focus", ("border-color",), _FIELD),
        (f"{_FIELD}:focus", ("box-shadow",), ".card"),
    ],
    ids=["field-edge-on-field", "field-edge-on-card", "focus-edge-on-field", "focus-ring-on-card"],
)
def test_password_gate_field_edge_and_focus_stand_out(theme: Theme, mark: str, props: tuple[str, ...], surface: str) -> None:
    assert_visible(render_password_gate_html(), theme, mark, props, surface)


def test_the_focused_field_keeps_an_outline_that_forced_colour_modes_draw() -> None:
    # Those modes drop the ring's box-shadow; a transparent outline is what they paint in its place.
    focus_rule = re.search(rf"{re.escape(_FIELD)}:focus\{{[^}}]*\}}", stylesheet(render_password_gate_html()))

    assert focus_rule is not None
    assert "outline:2px solid transparent" in focus_rule.group(0)


@_THEMES
@pytest.mark.parametrize(
    ("text", "surface"),
    [("body", ".card"), ("p", ".card"), (".brand", ".card")],
    ids=["title", "message", "brand"],
)
def test_status_page_text_is_readable_on_its_surface(theme: Theme, text: str, surface: str) -> None:
    assert_readable(render_share_status_html(ShareLinkState.EXPIRED), theme, text, surface)
