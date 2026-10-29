"""The unlock page of an encrypted publish keeps its text readable and its button, field edge and focus mark visible."""

from __future__ import annotations

import re

import pytest

from app.services.hosting.crypto_packager import package_encrypted_publish_files
from app.services.hosting.packager import PublishFile
from tests.support.wcag_contrast import Theme, assert_readable, assert_visible, stylesheet

# The page ships one palette and no prefers-color-scheme block, so the helper reads its single stylesheet as its
# "light" half. test_the_page_has_one_palette fails when a second one appears, so no theme goes unchecked.
_THEME: Theme = "light"
_FIELD = 'input[type="password"]'


@pytest.fixture(scope="module")
def page() -> str:
    files = {"index.html": PublishFile(path="index.html", content="<h1>Secret</h1>", encoding="utf-8")}
    return package_encrypted_publish_files(files, "any-password")["index.html"].content


def _rule(page: str, selector: str) -> str:
    found = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{[^}}]*\}}", stylesheet(page))
    assert found is not None, f"the page has no rule for {selector}"
    return found.group(0)


def test_the_page_has_one_palette(page: str) -> None:
    assert "prefers-color-scheme" not in stylesheet(page)


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
    ],
    ids=["title", "prompt", "error", "typed-text", "button", "button-hover", "button-disabled"],
)
def test_text_is_readable_on_its_surface(page: str, text: str, surface: str) -> None:
    assert_readable(page, _THEME, text, surface)


def test_the_placeholder_is_readable_in_the_field(page: str) -> None:
    assert_readable(page, _THEME, f"{_FIELD}::placeholder", _FIELD)


def test_the_placeholder_is_not_dimmed_below_its_colour(page: str) -> None:
    # Some browsers fade a placeholder by default; the colour that was checked must be the one painted.
    assert re.search(r"opacity:\s*1\s*;", _rule(page, f"{_FIELD}::placeholder"))


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
    assert_visible(page, _THEME, mark, props, surface)


def test_the_focused_field_keeps_an_outline_that_forced_colour_modes_draw(page: str) -> None:
    # Those modes drop the halo's box-shadow; a transparent outline is what they paint in its place.
    assert re.search(r"outline:\s*2px solid transparent\s*;", _rule(page, f"{_FIELD}:focus"))
