"""Tests for Feishu doc block → markdown conversion and image localization."""

from __future__ import annotations

import re

from app.services.wiki.source_sync.feishu import feishu_docx_blocks_to_markdown

# block_type enum (Feishu OpenAPI)
_B_TEXT = 2
_B_HEADING1 = 3
_B_BULLET = 12
_B_ORDERED = 13
_B_CODE = 14
_B_QUOTE = 15
_B_TODO = 17
_B_CALLOUT = 19
_B_DIVIDER = 22
_B_IMAGE = 27
_B_LINK_PREVIEW = 48
_B_AGENDA_ITEM_TITLE = 46


def _block(
    block_type: int, field: str, content: str, block_id: str, parent: str = ""
) -> dict[str, object]:
    return {
        "block_id": block_id,
        "block_type": block_type,
        "parent_id": parent,
        field: {"elements": [{"text_run": {"content": content}}]},
    }


def _payload(items: list[dict[str, object]]) -> dict[str, object]:
    return {"code": 0, "data": {"items": items}}


def test_text_and_heading() -> None:
    payload = _payload(
        [
            _block(_B_HEADING1, "heading1", "Title", "h1"),
            _block(_B_TEXT, "text", "Body paragraph", "p1"),
            _block(_B_BULLET, "bullet", "Bullet item", "b1"),
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "# Title" in text
    assert "Body paragraph" in text
    assert "- Bullet item" in text


def test_heading_1_to_9_levels() -> None:
    items = [
        _block(_B_HEADING1, "heading1", "H1", "h1"),
        _block(5, "heading3", "H3", "h3"),
        _block(6, "heading4", "H4", "h4"),
        _block(11, "heading9", "H9", "h9"),
    ]
    text = feishu_docx_blocks_to_markdown(_payload(items))
    assert text is not None
    assert "# H1" in text
    assert "### H3" in text
    assert "#### H4" in text
    assert "######### H9" in text


def test_ordered_list_counts_across_blocks() -> None:
    payload = _payload(
        [
            _block(_B_ORDERED, "ordered", "First", "o1"),
            _block(_B_ORDERED, "ordered", "Second", "o2"),
            _block(_B_BULLET, "bullet", "interrupt", "i1"),
            _block(_B_ORDERED, "ordered", "Restart", "o3"),
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "1. First" in text
    assert "2. Second" in text
    assert "- interrupt" in text
    assert "1. Restart" in text


def test_nested_bullet_list_indents() -> None:
    payload = _payload(
        [
            {
                "block_id": "L1",
                "block_type": _B_BULLET,
                "parent_id": "",
                "children": ["L1a"],
                "bullet": {"elements": [{"text_run": {"content": "lvl1"}}]},
            },
            {
                "block_id": "L1a",
                "block_type": _B_BULLET,
                "parent_id": "L1",
                "children": ["L1a1"],
                "bullet": {"elements": [{"text_run": {"content": "lvl2"}}]},
            },
            {
                "block_id": "L1a1",
                "block_type": _B_BULLET,
                "parent_id": "L1a",
                "bullet": {"elements": [{"text_run": {"content": "lvl3"}}]},
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "- lvl1\n  - lvl2\n    - lvl3" == text


def test_nested_ordered_list_restarts_counter_per_group() -> None:
    payload = _payload(
        [
            {
                "block_id": "O1",
                "block_type": _B_ORDERED,
                "parent_id": "",
                "children": ["O1a", "O1b"],
                "ordered": {"elements": [{"text_run": {"content": "parent1"}}]},
            },
            {
                "block_id": "O1a",
                "block_type": _B_ORDERED,
                "parent_id": "O1",
                "ordered": {"elements": [{"text_run": {"content": "child1"}}]},
            },
            {
                "block_id": "O1b",
                "block_type": _B_ORDERED,
                "parent_id": "O1",
                "ordered": {"elements": [{"text_run": {"content": "child2"}}]},
            },
            {
                "block_id": "O2",
                "block_type": _B_ORDERED,
                "parent_id": "",
                "ordered": {"elements": [{"text_run": {"content": "parent2"}}]},
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "1. parent1\n  1. child1\n  2. child2\n2. parent2" == text


def test_code_block_renders_fence_with_language() -> None:
    payload = _payload(
        [
            {
                "block_id": "c1",
                "block_type": _B_CODE,
                "parent_id": "",
                "code": {
                    "language": "python",
                    "elements": [{"text_run": {"content": "def f():\n    pass"}}],
                },
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "```python" in text
    assert "def f():" in text
    assert "```" in text


def test_quote_and_callout_render_blockquote() -> None:
    payload = _payload(
        [
            _block(_B_QUOTE, "quote", "Quoted line", "q1"),
            _block(_B_CALLOUT, "callout", "Callout line", "c1"),
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "> Quoted line" in text
    assert "> Callout line" in text


def test_todo_renders_checkbox_state() -> None:
    payload = _payload(
        [
            {
                "block_id": "t1",
                "block_type": _B_TODO,
                "parent_id": "",
                "todo": {
                    "done": True,
                    "elements": [{"text_run": {"content": "Done task"}}],
                },
            },
            {
                "block_id": "t2",
                "block_type": _B_TODO,
                "parent_id": "",
                "todo": {
                    "done": False,
                    "elements": [{"text_run": {"content": "Pending task"}}],
                },
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "- [x] Done task" in text
    assert "- [ ] Pending task" in text


def test_divider_renders_horizontal_rule() -> None:
    text = feishu_docx_blocks_to_markdown(
        _payload(
            [
                {
                    "block_id": "d1",
                    "block_type": _B_DIVIDER,
                    "parent_id": "",
                    "divider": {},
                }
            ]
        )
    )
    assert text is not None
    assert text == "---"


def test_image_emits_asset_placeholder() -> None:
    payload = _payload(
        [
            {
                "block_id": "img1",
                "block_type": _B_IMAGE,
                "parent_id": "",
                "image": {"token": "img_v2_abc123"},
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "![image](feishu-image:img_v2_abc123)" in text


def test_link_preview_renders_markdown_link() -> None:
    payload = _payload(
        [
            {
                "block_id": "lp1",
                "block_type": _B_LINK_PREVIEW,
                "parent_id": "",
                "link_preview": {
                    "url": "https%3A%2F%2Fexample.com%2Fdocs",
                    "title": "Example Doc",
                },
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "[Example Doc](<https://example.com/docs>)" in text


def test_inline_styles_link_and_code_use_official_api_structure() -> None:
    payload = _payload(
        [
            {
                "block_id": "p1",
                "block_type": _B_TEXT,
                "parent_id": "",
                "text": {
                    "elements": [
                        {
                            "text_run": {
                                "content": "bold text",
                                "text_element_style": {"bold": True},
                            }
                        },
                        {
                            "text_run": {
                                "content": "code",
                                "text_element_style": {"inline_code": True},
                            }
                        },
                        {
                            "text_run": {
                                "content": "link text",
                                "text_element_style": {
                                    "link": {"url": "https%3A%2F%2Fexample.com%2Fpath"}
                                },
                            }
                        },
                    ]
                },
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "**bold text**" in text
    assert "`code`" in text
    assert "[link text](<https://example.com/path>)" in text


def test_agenda_item_title_renders_text() -> None:
    payload = _payload(
        [
            {
                "block_id": "ag1",
                "block_type": _B_AGENDA_ITEM_TITLE,
                "parent_id": "",
                "agenda_item_title": {
                    "elements": [{"text_run": {"content": "Agenda first item"}}]
                },
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "Agenda first item" in text


def test_unknown_block_falls_back_to_inline_text() -> None:
    payload = _payload(
        [
            {
                "block_id": "u1",
                "block_type": 99,
                "parent_id": "",
                "text": {
                    "elements": [{"text_run": {"content": "unknown fallback"}}],
                },
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "unknown fallback" in text


def test_invalid_payload_returns_none() -> None:
    assert feishu_docx_blocks_to_markdown({"code": 0}) is None
    assert feishu_docx_blocks_to_markdown({"data": {"items": "nope"}}) is None
    assert feishu_docx_blocks_to_markdown({"data": {}}) is None


def test_null_content_and_styles_degrade_gracefully() -> None:
    payload = _payload(
        [
            {
                "block_id": "p1",
                "block_type": _B_TEXT,
                "parent_id": "",
                "text": {
                    "elements": [
                        {"text_run": {"content": None}},
                        {"text_run": {}},
                        {"text_run": {"content": "kept", "text_element_style": None}},
                    ]
                },
            },
            {
                "block_id": "img1",
                "block_type": _B_IMAGE,
                "parent_id": "",
                "image": {"token": None},
            },
            {
                "block_id": "lp1",
                "block_type": _B_LINK_PREVIEW,
                "parent_id": "",
                "link_preview": {"url": None, "title": "no url"},
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "None" not in text
    assert "kept" in text
    assert "no url" in text
    assert "feishu-image:" not in text


def test_inline_code_wraps_nested_backticks() -> None:
    payload = _payload(
        [
            {
                "block_id": "p1",
                "block_type": _B_TEXT,
                "parent_id": "",
                "text": {
                    "elements": [
                        {
                            "text_run": {
                                "content": "a ` b",
                                "text_element_style": {"inline_code": True},
                            }
                        },
                    ]
                },
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "``a ` b``" in text


def test_code_block_fence_adapts_to_backtick_runs() -> None:
    """Code containing triple backticks (e.g. embedded markdown) must not
    terminate the code fence early."""
    payload = _payload(
        [
            {
                "block_id": "c1",
                "block_type": _B_CODE,
                "parent_id": "",
                "code": {
                    "language": "markdown",
                    "elements": [{"text_run": {"content": "```python\nprint(1)\n```"}}],
                },
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "````markdown" in text
    assert text.rstrip().endswith("````")


def test_plain_dollar_sign_is_escaped() -> None:
    """Literal $ in body text must be escaped so rehype-katex (singleDollarTextMath)
    does not mis-parse prices/variables as formulas."""
    payload = _payload(
        [
            _block(_B_TEXT, "text", "cost $100 per unit", "p1"),
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "cost \\$100 per unit" in text


def test_file_block_renders_display_name() -> None:
    """Feishu file blocks (video/attachment) carry a name; render it so the
    file reference is not silently dropped."""
    payload = _payload(
        [
            {
                "block_id": "f1",
                "block_type": 23,
                "parent_id": "",
                "file": {"token": "tok_video", "name": "demo.mp4", "view_type": 1},
            },
            {
                "block_id": "f2",
                "block_type": 23,
                "parent_id": "",
                "file": {"token": "tok_nameless"},
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "文件: demo.mp4" in text
    assert "文件" in text


def test_mention_and_equation_elements_are_rendered() -> None:
    """Real Feishu TextElement types (mention_user/mention_doc/reminder/equation)."""
    payload = _payload(
        [
            {
                "block_id": "p1",
                "block_type": _B_TEXT,
                "parent_id": "",
                "text": {
                    "elements": [
                        {"mention_user": {"user_id": "ou_123"}},
                        {"text_run": {"content": " reviewed "}},
                        {
                            "mention_doc": {
                                "token": "doc_abc",
                                "obj_type": 1,
                                "url": "https%3A%2F%2Ffeishu.cn%2Fwiki%2Fabc",
                            }
                        },
                        {"text_run": {"content": " "}},
                        {"reminder": {"expire_time": 1_752_000_000_000}},
                        {"text_run": {"content": " "}},
                        {"equation": {"content": r"E=mc^2"}},
                    ]
                },
            },
        ]
    )
    text = feishu_docx_blocks_to_markdown(payload)
    assert text is not None
    assert "@用户" in text
    assert "[@文档](<https://feishu.cn/wiki/abc>)" in text
    assert re.search(r"@\d{4}-\d{2}-\d{2}", text) is not None
    assert "$E=mc^2$" in text
