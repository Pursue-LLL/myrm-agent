"""The password-gate and status pages keep their text readable on what it sits on, in both themes."""

from __future__ import annotations

import pytest

from app.core.security.share.share_password_page import render_password_gate_html
from app.core.security.share.share_status_page import ShareLinkState, render_share_status_html
from tests.support.wcag_contrast import Theme, assert_readable

_THEMES = pytest.mark.parametrize("theme", ["light", "dark"])


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
@pytest.mark.parametrize(
    ("text", "surface"),
    [("body", ".card"), ("p", ".card"), (".brand", ".card")],
    ids=["title", "message", "brand"],
)
def test_status_page_text_is_readable_on_its_surface(theme: Theme, text: str, surface: str) -> None:
    assert_readable(render_share_status_html(ShareLinkState.EXPIRED), theme, text, surface)
