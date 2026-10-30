"""Tests for markdown frontmatter helpers."""

from __future__ import annotations

import pytest

from myrm_agent_harness.utils.markdown_frontmatter import (
    extract_frontmatter_block,
    has_frontmatter_block,
    parse_frontmatter,
    preserve_frontmatter_on_edit,
)


def test_parse_frontmatter_inline_tags() -> None:
    content = "---\ntags: [python, web]\n---\n# Hello\n"
    meta, body = parse_frontmatter(content)
    assert meta["tags"] == ["python", "web"]
    assert body.startswith("# Hello")


def test_preserve_frontmatter_on_edit_reinjects_block() -> None:
    pre = "---\ndate: 2026-07-28\ntags: [daily]\n---\n# Title\n\nOld body\n"
    post = "# Title\n\nNew body\n"
    merged, warnings = preserve_frontmatter_on_edit(pre, post)
    assert has_frontmatter_block(merged)
    assert "date: 2026-07-28" in merged
    assert "New body" in merged
    assert warnings


def test_preserve_frontmatter_on_edit_keeps_explicit_frontmatter() -> None:
    pre = "---\ndate: old\n---\n# Title\n"
    post = "---\ndate: new\n---\n# Title\n"
    merged, warnings = preserve_frontmatter_on_edit(pre, post)
    assert merged == post
    assert not warnings


def test_has_and_extract_frontmatter_block() -> None:
    content = "---\ntags: [x]\n---\nbody"
    assert has_frontmatter_block(content)
    assert extract_frontmatter_block(content) == "---\ntags: [x]\n---\n"
    assert has_frontmatter_block("plain body") is False
    assert extract_frontmatter_block("plain body") is None


def test_parse_frontmatter_no_block() -> None:
    meta, body = parse_frontmatter("plain body\n")
    assert meta == {}
    assert body == "plain body\n"


def test_parse_frontmatter_rich_lines() -> None:
    content = "\n".join(
        [
            "---",
            "# generated comment",
            "date: 2026-07-28",
            'quoted: "some value"',
            "empty_key:",
            "  - alpha",
            "  - beta",
            "list_inline: [a, b]",
            "bare-odd-line",
            "plain: value",
            "---",
            "# Body",
        ]
    )
    meta, body = parse_frontmatter(content)
    assert meta["date"] == "2026-07-28"
    assert meta["quoted"] == "some value"
    assert meta["empty_key"] == ["alpha", "beta"]
    assert meta["list_inline"] == ["a", "b"]
    assert meta["plain"] == "value"
    assert "empty_key" in meta
    assert body.startswith("# Body")


def test_parse_frontmatter_quoted_single_value() -> None:
    meta, _body = parse_frontmatter("---\nname: 'single'\n---\n")
    assert meta["name"] == "single"


def test_preserve_frontmatter_on_edit_without_pre_block() -> None:
    merged, warnings = preserve_frontmatter_on_edit("no frontmatter", "post\n")
    assert merged == "post\n"
    assert not warnings


@pytest.mark.parametrize("bom", ["", "\ufeff"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_frontmatter_block_is_found_with_or_without_a_leading_bom(bom: str, newline: str) -> None:
    block = newline.join(["---", "title: Roadmap", "publish_status: draft", "---", ""])
    content = f"{bom}{block}# Body{newline}"

    meta, body = parse_frontmatter(content)

    assert meta == {"title": "Roadmap", "publish_status": "draft"}
    assert body == f"# Body{newline}"
    assert has_frontmatter_block(content)
    assert extract_frontmatter_block(content) == f"{bom}{block}"


def test_preserve_frontmatter_on_edit_reinjects_a_block_that_starts_with_a_bom() -> None:
    pre = "\ufeff---\ndate: 2026-07-28\n---\n# Title\n\nOld body\n"
    merged, warnings = preserve_frontmatter_on_edit(pre, "# Title\n\nNew body\n")

    assert merged == "\ufeff---\ndate: 2026-07-28\n---\n# Title\n\nNew body\n"
    assert warnings


def test_preserve_frontmatter_on_edit_keeps_an_edit_that_starts_with_a_bom() -> None:
    post = "\ufeff---\ndate: new\n---\n# Title\n"
    merged, warnings = preserve_frontmatter_on_edit("---\ndate: old\n---\n# Title\n", post)

    assert merged == post
    assert not warnings
