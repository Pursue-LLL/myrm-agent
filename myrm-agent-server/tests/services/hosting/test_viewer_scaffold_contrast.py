"""The standalone document viewer keeps the text of its header, buttons and download card readable.

The two tinted badges (the ARTIFACT tag and the DOCUMENT ARTIFACT label) sit on translucent fills that the contrast
helper cannot read, so they are not covered here.
"""

from __future__ import annotations

import pytest

from app.services.hosting.viewer_scaffold import render_standalone_viewer_html
from tests.support.wcag_contrast import Theme, assert_readable, stylesheet

# The page ships one palette and no prefers-color-scheme block, so the helper reads its single stylesheet as its
# "light" half. test_the_page_has_one_palette fails when a second one appears, so no theme goes unchecked.
_THEME: Theme = "light"


@pytest.fixture(scope="module")
def page() -> str:
    return render_standalone_viewer_html("report.docx")


def test_the_page_has_one_palette(page: str) -> None:
    assert "prefers-color-scheme" not in stylesheet(page)
    assert 'class="doc-meta"' in page


@pytest.mark.parametrize(
    ("text", "surface"),
    [
        (".brand", "header"),
        (".btn-dl", ".btn-dl"),
        (".btn-dl:hover", ".btn-dl:hover"),
        (".btn-raw", ".btn-raw"),
        (".btn-raw", ".btn-raw:hover"),
        (".doc-title", ".doc-card"),
        (".doc-filename", ".doc-card"),
        (".doc-filename code", ".doc-filename code"),
        (".doc-meta", ".doc-card"),
        (".btn-primary", ".btn-primary"),
        (".btn-primary", ".btn-primary:hover"),
    ],
    ids=[
        "brand",
        "download",
        "download-hover",
        "open-raw",
        "open-raw-hover",
        "card-title",
        "card-filename",
        "card-filename-code",
        "card-meta",
        "card-button",
        "card-button-hover",
    ],
)
def test_text_is_readable_on_its_surface(page: str, text: str, surface: str) -> None:
    assert_readable(page, _THEME, text, surface)
