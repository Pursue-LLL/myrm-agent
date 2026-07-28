"""Tests for md_to_wechat_html formatter script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

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
    assert "<h1>" in html
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
    assert "<table>" in html
    assert "<th>" in html
    assert html.count("<li>") >= 2
    assert "<ul>" in html
    assert "print('wechat')" in html or "print(&#x27;wechat&#x27;)" in html or "&#39;wechat&#39;" in html
    assert "<pre>" in html
    assert 'style="color:' in html or 'class="highlight"' in html


def test_md_to_wechat_html_syntax_highlights_python(tmp_path: Path) -> None:
    source = tmp_path / "code.md"
    source.write_text("```python\ndef greet(name: str) -> str:\n    return f'hi {name}'\n```\n", encoding="utf-8")
    output = tmp_path / "code.wechat.html"

    html = _run_formatter(source, output)
    assert "def" in html
    assert "greet" in html
    assert 'style="color:' in html or 'class="k"' in html or 'class="nf"' in html
