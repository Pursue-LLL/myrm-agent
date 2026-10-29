"""The WebUI welcome page: the address it shows, how it encodes that address, and that its text and buttons stay readable."""

from __future__ import annotations

import re

import pytest

from app.api.webui.welcome_page import render_welcome_page
from tests.support.wcag_contrast import (
    SINGLE_PALETTE,
    assert_readable,
    assert_single_palette,
    assert_visible,
)


@pytest.fixture(scope="module")
def page() -> str:
    return render_welcome_page("192.168.1.100", 25808)


def test_the_page_shows_its_address_and_links_the_qr_code_to_it(page: str) -> None:
    assert '<p class="url">http://192.168.1.100:25808</p>' in page
    assert '<img src="/api/v1/webui/qrcode.png?host=192.168.1.100&amp;port=25808" alt="QR Code">' in page
    assert 'link.href = "/api/v1/webui/qrcode.png?host=192.168.1.100&port=25808";' in page


def test_a_host_cannot_bring_markup_into_the_page() -> None:
    payload = '"><script>alert(1)</script>'
    page = render_welcome_page(payload, 25808)
    assert payload not in page
    assert "%22%3E%3Cscript%3Ealert%281%29%3C%2Fscript%3E" in page
    assert "http://&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;:25808" in page
    assert page.count("<script>") == 1 and page.count("</script>") == 1


def test_the_page_has_one_palette(page: str) -> None:
    assert_single_palette(page)


@pytest.mark.parametrize(
    ("text", "surface"),
    [
        ("h1", ".container"),
        (".subtitle", ".container"),
        (".qr-section h2", ".qr-section"),
        (".url", ".qr-section"),
        (".btn-primary", ".btn-primary"),
        (".btn-primary", ".btn-primary:hover"),
        (".btn-secondary", ".btn-secondary"),
        (".btn-secondary", ".btn-secondary:hover"),
        (".info", ".info"),
    ],
    ids=["title", "subtitle", "qr-heading", "address", "open", "open-hover", "download", "download-hover", "tip"],
)
def test_text_is_readable_on_its_surface(page: str, text: str, surface: str) -> None:
    assert_readable(page, SINGLE_PALETTE, text, surface)


def test_the_download_button_edge_and_the_focus_ring_stand_out(page: str) -> None:
    assert_visible(page, SINGLE_PALETTE, ".btn-secondary", ("border-color", "border"), ".container")
    assert_visible(page, SINGLE_PALETTE, "button:focus-visible", ("outline",), ".container")


def test_no_colour_is_set_outside_the_stylesheet(page: str) -> None:
    markup = page.split("</style>")[1]
    assert not re.search(r"\bstyle\s*=|\.style\.", markup)
