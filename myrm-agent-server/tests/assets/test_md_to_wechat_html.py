"""Tests for md_to_wechat_html formatter script."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("markdown", reason="requires uv sync --extra wechat-formatter")

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "wechat-article-formatter"
    / "scripts"
    / "md_to_wechat_html.py"
)


def _run_formatter(source: Path, output: Path) -> str:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(source), "-o", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert output.is_file()
    return output.read_text(encoding="utf-8")


def test_md_to_wechat_html_generates_styled_output(tmp_path: Path) -> None:
    source = tmp_path / "post.md"
    source.write_text("# Hello WeChat\n\nParagraph with **bold**.\n", encoding="utf-8")
    output = tmp_path / "post.wechat.html"

    html = _run_formatter(source, output)
    assert "<h1" in html
    assert "Hello WeChat" in html
    assert "font-family" in html
    assert "PingFang SC" in html


def test_md_to_wechat_html_golden_tables_lists_and_code(tmp_path: Path) -> None:
    source = tmp_path / "golden.md"
    source.write_text(
        "# Golden Article\n\n"
        "- alpha\n"
        "- beta\n\n"
        "| Name | Value |\n"
        "| --- | --- |\n"
        "| foo | 1 |\n\n"
        "```python\nprint('wechat')\n```\n",
        encoding="utf-8",
    )
    output = tmp_path / "golden.wechat.html"

    html = _run_formatter(source, output)
    assert "<table" in html
    assert "<th" in html
    assert html.count("<li>") >= 2
    assert "<ul>" in html
    assert "print('wechat')" in html or "print(&#x27;wechat&#x27;)" in html or "&#39;wechat&#x27;" in html or "wechat" in html
    assert "<code>" in html
    assert 'style="color:' in html or 'class="highlight"' in html


def test_md_to_wechat_html_syntax_highlights_python(tmp_path: Path) -> None:
    source = tmp_path / "code.md"
    source.write_text("```python\ndef greet(name: str) -> str:\n    return f'hi {name}'\n```\n", encoding="utf-8")
    output = tmp_path / "code.wechat.html"

    html = _run_formatter(source, output)
    assert "def" in html
    assert "greet" in html
    assert 'style="color:' in html or 'class="k"' in html or 'class="nf"' in html


def test_md_to_wechat_html_block_elements_have_inline_styles(tmp_path: Path) -> None:
    source = tmp_path / "blocks.md"
    source.write_text(
        "## Section Title\n\nParagraph text.\n\n> A quote\n\n"
        "| Name | Value |\n| --- | --- |\n| foo | 1 |\n",
        encoding="utf-8",
    )
    output = tmp_path / "blocks.wechat.html"

    html = _run_formatter(source, output)
    assert re.search(
        r'<h2[^>]+style="[^"]*border-left:\s*4px\s+solid\s+#07c160',
        html,
        re.IGNORECASE,
    )
    assert re.search(r'<p[^>]+style="[^"]*text-align:\s*justify', html, re.IGNORECASE)
    assert re.search(r'<blockquote[^>]+style="[^"]*background:\s*#f6f6f6', html, re.IGNORECASE)
    assert re.search(r'<table[^>]+style="[^"]*border-collapse:\s*collapse', html, re.IGNORECASE)
    assert re.search(r'<th[^>]+style="[^"]*background:\s*#f7f7f7', html, re.IGNORECASE)


def test_md_to_wechat_html_css_generated_from_block_inline_styles(tmp_path: Path) -> None:
    source = tmp_path / "post.md"
    source.write_text("# Title\n\n![hero](./hero.png)\n", encoding="utf-8")
    (tmp_path / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    output = tmp_path / "post.wechat.html"

    html = _run_formatter(source, output)
    assert "border-left: 4px solid #07c160" in html
    assert re.search(r'<h1[^>]+style="[^"]*text-align:\s*center', html, re.IGNORECASE)
    assert re.search(r'<img[^>]+style="[^"]*max-width:\s*100%', html, re.IGNORECASE)


def test_formatter_output_flows_to_draft_content_with_inline_styles(tmp_path: Path) -> None:
    from app.channels.providers.wechat.draft_service import _build_draft_content

    (tmp_path / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    source = tmp_path / "article.md"
    source.write_text("## Section\n\nBody text.\n\n![hero](./hero.png)\n", encoding="utf-8")
    output = tmp_path / "article.wechat.html"

    html = _run_formatter(source, output)
    draft_content = _build_draft_content(html)
    assert "border-left: 4px solid #07c160" in draft_content
    assert re.search(r'<img[^>]+style="[^"]*max-width:\s*100%', draft_content, re.IGNORECASE)
    assert "<!DOCTYPE" not in draft_content
