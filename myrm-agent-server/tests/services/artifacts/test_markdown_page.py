"""The Markdown artifact share page: a readable, script-free document, readable in both themes, and capped in size."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.security.share.share_locale import HTML_LANG, SHARE_BRAND, ShareLang
from app.services.artifacts.share import markdown_page
from app.services.artifacts.share.markdown_page import is_markdown_media_type, render_markdown_share_page
from tests.support.wcag_contrast import Theme, assert_readable, declared_value, split_themes, stylesheet

_THEMES = pytest.mark.parametrize("theme", ["light", "dark"])
_REPORT = "# Quarterly report\n\nAll **deliverables** shipped.\n\n- one\n- two\n\n```python\nprint('hi')\n```\n\n> quoted\n"


def _write(tmp_path: Path, text: str, name: str = "report.md") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


async def _page(tmp_path: Path, text: str = _REPORT, *, filename: str = "report.md", lang: ShareLang = "en") -> str:
    page = await render_markdown_share_page(_write(tmp_path, text), filename, lang)
    assert page is not None
    return page


@pytest.mark.parametrize(
    ("media_type", "expected"),
    [
        ("text/markdown", True),
        ("text/markdown; charset=utf-8", True),
        ("TEXT/Markdown", True),
        ("text/plain", False),
        ("text/html; charset=utf-8", False),
        ("application/pdf", False),
    ],
)
def test_only_markdown_media_types_are_rendered(media_type: str, expected: bool) -> None:
    assert is_markdown_media_type(media_type) is expected


async def test_the_page_shows_the_markdown_as_a_document(tmp_path: Path) -> None:
    page = await _page(tmp_path)

    assert "<h1>Quarterly report</h1>" in page
    assert "<strong>deliverables</strong>" in page
    assert "<ul>" in page
    assert "<pre><code" in page
    assert "<blockquote>" in page
    assert "<title>report</title>" in page


async def test_a_single_newline_inside_a_paragraph_is_not_a_line_break(tmp_path: Path) -> None:
    assert "<br" not in await _page(tmp_path, "one\ntwo")


async def test_the_page_runs_no_script_and_markup_in_the_text_is_escaped(tmp_path: Path) -> None:
    page = await _page(tmp_path, "<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[x](javascript:alert(1))")

    assert "<script" not in page
    assert "<img" not in page
    assert "<a " not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


async def test_the_title_comes_from_the_file_name_and_is_escaped(tmp_path: Path) -> None:
    page = await _page(tmp_path, filename='<b>"x"&.md')

    assert "<title>&lt;b&gt;&quot;x&quot;&amp;</title>" in page


@pytest.mark.parametrize("lang", ["en", "zh"])
async def test_the_page_chrome_follows_the_visitor_language(tmp_path: Path, lang: ShareLang) -> None:
    page = await _page(tmp_path, lang=lang)

    assert f'<html lang="{HTML_LANG[lang]}">' in page
    assert SHARE_BRAND[lang] in page


async def test_text_that_is_not_utf8_is_rendered_with_replacement_characters(tmp_path: Path) -> None:
    path = tmp_path / "legacy.md"
    path.write_bytes(b"# caf\xe9\n")

    page = await render_markdown_share_page(path, "legacy.md", "en")

    assert page is not None
    assert "<h1>caf\ufffd</h1>" in page


async def test_a_file_above_the_cap_is_not_rendered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(markdown_page, "_MAX_RENDERED_BYTES", 10)
    path = _write(tmp_path, "# a heading longer than ten bytes")

    assert await render_markdown_share_page(path, "report.md", "en") is None


async def test_a_file_at_the_cap_is_rendered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    text = "# 12345678"
    monkeypatch.setattr(markdown_page, "_MAX_RENDERED_BYTES", len(text.encode()))

    assert await render_markdown_share_page(_write(tmp_path, text), "report.md", "en") is not None


@_THEMES
@pytest.mark.parametrize(
    ("text", "surface"),
    [
        ("body", ".doc"),
        ("body", ".doc th"),
        (".doc code", ".doc code"),
        (".doc pre", ".doc pre"),
        (".doc blockquote", ".doc"),
        (".doc a", ".doc"),
        (".doc a", ".doc th"),
        (".footer", "body"),
    ],
    ids=["text", "table-header", "inline-code", "code-block", "quote", "link", "link-in-table-header", "footer"],
)
async def test_page_text_is_readable_on_its_surface(tmp_path: Path, theme: Theme, text: str, surface: str) -> None:
    assert_readable(await _page(tmp_path), theme, text, surface)


async def test_code_inside_a_block_keeps_the_block_text_colour(tmp_path: Path) -> None:
    """A block's code would otherwise take the inline-code colour and vanish on the dark block."""
    light, _ = split_themes(stylesheet(await _page(tmp_path)))

    assert declared_value(light, ".doc pre code", "color") == "inherit"
