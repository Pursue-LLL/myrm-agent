"""The Markdown renderer of every share page: nothing a model or a user writes becomes markup the page did not intend."""

from __future__ import annotations

import re

import pytest

from app.core.security.share.share_markdown import build_share_markdown


def _render(source: str, *, breaks: bool = False) -> str:
    html: str = build_share_markdown(breaks=breaks).render(source)
    return html


@pytest.mark.parametrize(
    "markup",
    [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "text <b onclick=alert(1)>bold</b> text",
        "<iframe src='https://evil.example'></iframe>",
        "<a href='javascript:alert(1)'>x</a>",
    ],
)
def test_raw_html_is_escaped_instead_of_rendered(markup: str) -> None:
    html = _render(markup)

    assert not re.search(r"<(script|img|b|iframe|a)\b", html)
    assert "&lt;" in html


@pytest.mark.parametrize(
    "destination",
    [
        "javascript:alert(1)",
        "JaVaScRiPt:alert(1)",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "data:text/html;base64,PHNjcmlwdD4=",
    ],
)
def test_a_link_or_image_to_a_dangerous_destination_is_not_made_markup(destination: str) -> None:
    html = _render(f"[open]({destination})\n\n![shown]({destination})")

    assert "<a " not in html
    assert "<img" not in html


def test_an_https_link_is_an_anchor() -> None:
    assert '<a href="https://example.com/guide">guide</a>' in _render("[guide](https://example.com/guide)")


def test_a_wide_table_is_wrapped_in_a_scrolling_box() -> None:
    html = _render("| Name | Path |\n|---|---|\n| a | /very/long/path |")

    assert re.search(r'<div class="table-wrap"><table>.*</table>\s*</div>', html, re.DOTALL)


def test_a_table_cell_cannot_inject_markup() -> None:
    html = _render("| a |\n|---|\n| <img src=x onerror=alert(1)> |")

    assert "<img" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_a_line_break_is_kept_for_conversations_and_ignored_for_documents() -> None:
    assert "<br" in _render("one\ntwo", breaks=True)
    assert "<br" not in _render("one\ntwo", breaks=False)
