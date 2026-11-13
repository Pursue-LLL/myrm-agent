"""Feishu text that carries Markdown goes out as a rich-text post whose elements mirror the Markdown spans."""

from __future__ import annotations

import pytest

from app.channels.providers.feishu.cards import build_post_content, has_rich_text, resolve_send_mode


def _paragraphs(content: str) -> list[list[dict[str, object]]]:
    post = build_post_content(content)
    return post["zh_cn"]["content"]


@pytest.mark.parametrize(
    "content",
    ["**bold**", "~~gone~~", "`code`", "[docs](https://x.dev)", "# Title", "###### Deepest", "plain\n## heading on line two"],
)
def test_markdown_spans_and_headings_make_a_message_rich(content: str) -> None:
    assert has_rich_text(content) is True


@pytest.mark.parametrize(
    "content",
    ["", "plain words", "snake_case_name stays plain", "2 * 3 * 4", "a # is not a heading", "####### seven hashes", "[x] (y)"],
)
def test_plain_text_stays_a_text_message(content: str) -> None:
    assert has_rich_text(content) is False


def test_the_post_payload_is_one_zh_cn_body_without_a_title() -> None:
    assert build_post_content("hello") == {"zh_cn": {"title": "", "content": [[{"tag": "text", "text": "hello"}]]}}


def test_each_markdown_span_becomes_its_post_element() -> None:
    assert _paragraphs("Hi **bold** and ~~gone~~, `code` or [docs](https://x.dev)!") == [
        [
            {"tag": "text", "text": "Hi "},
            {"tag": "text", "text": "bold", "style": ["bold"]},
            {"tag": "text", "text": " and "},
            {"tag": "text", "text": "gone", "style": ["lineThrough"]},
            {"tag": "text", "text": ", "},
            {"tag": "text", "text": "`code`"},
            {"tag": "text", "text": " or "},
            {"tag": "a", "text": "docs", "href": "https://x.dev"},
            {"tag": "text", "text": "!"},
        ]
    ]


def test_inline_code_keeps_its_backticks_because_a_post_has_no_code_style() -> None:
    """Feishu ignores a style it does not know, so a ``code`` style would show the span as plain text."""
    (paragraph,) = _paragraphs("run `make test` now")

    assert {"tag": "text", "text": "`make test`"} in paragraph
    assert all("style" not in element for element in paragraph)


def test_every_line_is_a_paragraph_and_a_blank_line_is_an_empty_one() -> None:
    assert _paragraphs("first\n\nthird") == [
        [{"tag": "text", "text": "first"}],
        [{"tag": "text", "text": ""}],
        [{"tag": "text", "text": "third"}],
    ]


@pytest.mark.parametrize("marks", ["#", "###", "######"])
def test_a_heading_is_bold_whatever_its_level(marks: str) -> None:
    assert _paragraphs(f"{marks} Overview") == [[{"tag": "text", "text": "Overview", "style": ["bold"]}]]


def test_a_heading_shows_its_inline_spans_instead_of_their_markup() -> None:
    """``### 1. **Overview**`` is a common heading shape; the asterisks must not reach the reader."""
    assert _paragraphs("### 1. **Overview** and [docs](https://x.dev)") == [
        [
            {"tag": "text", "text": "1. ", "style": ["bold"]},
            {"tag": "text", "text": "Overview", "style": ["bold"]},
            {"tag": "text", "text": " and ", "style": ["bold"]},
            {"tag": "a", "text": "docs", "href": "https://x.dev", "style": ["bold"]},
        ]
    ]


def test_a_heading_keeps_the_other_styles_of_its_spans() -> None:
    assert _paragraphs("## ~~old~~") == [[{"tag": "text", "text": "old", "style": ["bold", "lineThrough"]}]]


@pytest.mark.parametrize(
    ("reply_to_id", "root_id", "mode"),
    [
        ("om_1", "om_root", "reply"),
        ("om_1", None, "reply"),
        (None, "om_root", "root_create"),
        (None, None, "create"),
        ("", "", "create"),
    ],
)
def test_a_reply_beats_a_thread_root_and_both_beat_a_new_message(reply_to_id: str | None, root_id: str | None, mode: str) -> None:
    assert resolve_send_mode(reply_to_id=reply_to_id, root_id=root_id) == mode
