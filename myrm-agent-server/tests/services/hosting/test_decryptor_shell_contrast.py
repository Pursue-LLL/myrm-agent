"""The unlock page of an encrypted publish keeps its text readable and its button, field edge and focus mark visible."""

from __future__ import annotations

import re

import pytest

from app.services.hosting.crypto_packager import package_encrypted_publish_files
from app.services.hosting.packager import PublishFile
from tests.support.wcag_contrast import (
    SINGLE_PALETTE,
    assert_readable,
    assert_single_palette,
    assert_visible,
    declared_value,
    stylesheet,
)

_FIELD = 'input[type="password"]'


@pytest.fixture(scope="module")
def page() -> str:
    files = {"index.html": PublishFile(path="index.html", content="<h1>Secret</h1>", encoding="utf-8")}
    return package_encrypted_publish_files(files, "any-password")["index.html"].content


def test_the_page_has_one_palette(page: str) -> None:
    assert_single_palette(page)


@pytest.mark.parametrize(
    ("text", "surface"),
    [
        ("h1", ".card"),
        ("p", ".card"),
        (".error", ".card"),
        (_FIELD, _FIELD),
        ("button", "button"),
        ("button", "button:hover"),
        ("button", "button:disabled"),
        (".notice", ".notice"),
        (".fatal", "body.unlocked"),
    ],
    ids=["title", "prompt", "error", "typed-text", "button", "button-hover", "button-disabled", "notice", "bundle-error"],
)
def test_text_is_readable_on_its_surface(page: str, text: str, surface: str) -> None:
    assert_readable(page, SINGLE_PALETTE, text, surface)


def test_the_placeholder_is_readable_in_the_field(page: str) -> None:
    assert_readable(page, SINGLE_PALETTE, f"{_FIELD}::placeholder", _FIELD)


def test_the_placeholder_is_not_dimmed_below_its_colour(page: str) -> None:
    # Some browsers fade a placeholder by default; the colour that was checked must be the one painted.
    assert declared_value(stylesheet(page), f"{_FIELD}::placeholder", "opacity") == "1"


@pytest.mark.parametrize(
    ("mark", "props", "surface"),
    [
        (_FIELD, ("border-color", "border"), _FIELD),
        (_FIELD, ("border-color", "border"), ".card"),
        (f"{_FIELD}:focus", ("border-color",), _FIELD),
        (f"{_FIELD}:focus", ("border-color",), ".card"),
    ],
    ids=["field-edge-on-field", "field-edge-on-card", "focus-edge-on-field", "focus-edge-on-card"],
)
def test_field_edge_and_focus_stand_out(page: str, mark: str, props: tuple[str, ...], surface: str) -> None:
    assert_visible(page, SINGLE_PALETTE, mark, props, surface)


def test_the_focused_field_keeps_an_outline_that_forced_colour_modes_draw(page: str) -> None:
    # Those modes drop the halo's box-shadow; a transparent outline is what they paint in its place.
    assert declared_value(stylesheet(page), f"{_FIELD}:focus", "outline") == "2px solid transparent"


def test_no_colour_is_set_outside_the_stylesheet(page: str) -> None:
    # A colour written into an inline style or assigned by the script is invisible to the checks above.
    markup = page.split("</style>")[1]
    inline = re.findall(r"""style\s*=\s*["'][^"']*(?:color|background)""", markup)
    scripted = re.findall(r"\.style\.(?:color|background\w*)\b", markup)
    assert not inline and not scripted
