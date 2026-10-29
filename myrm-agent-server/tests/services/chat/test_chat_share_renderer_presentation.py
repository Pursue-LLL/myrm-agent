"""Tests for how the shared conversation page presents tables, links and its small text."""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from tests.services.chat.share_support import agentless_db, make_message, render_page
from tests.support.wcag_contrast import Theme, assert_readable, effective, split_themes, stylesheet

_TABLE = "| Name | Path |\n|---|---|\n| a | /very/long/path |"
_WRAPPED_TABLE = re.compile(r'<div class="table-wrap"><table>.*?</table>\s*</div>', re.DOTALL)


@pytest.fixture
def mock_db() -> MagicMock:
    return agentless_db()


async def test_a_table_in_an_assistant_message_scrolls_inside_its_bubble(mock_db: MagicMock) -> None:
    html = await render_page(mock_db, "en", messages=[make_message("m1", "assistant", f"{_TABLE}\n\ntext\n\n{_TABLE}")])

    assert html.count("<table>") == 2
    assert len(_WRAPPED_TABLE.findall(html)) == 2


async def test_a_pipe_table_typed_by_the_user_stays_plain_text(mock_db: MagicMock) -> None:
    html = await render_page(mock_db, "en", messages=[make_message("m1", "user", _TABLE)])

    assert "<table>" not in html
    assert "table-wrap" not in html.split("</style>")[1]


async def test_a_table_cell_cannot_inject_markup(mock_db: MagicMock) -> None:
    cell = "<img src=x onerror=alert(1)>"
    html = await render_page(mock_db, "en", messages=[make_message("m1", "assistant", f"| a |\n|---|\n| {cell} |")])

    body = html.split("</style>")[1]
    assert "<img" not in body
    assert "&lt;img src=x onerror=alert(1)&gt;" in body


async def test_a_markdown_link_in_an_assistant_message_is_an_anchor_and_one_typed_by_the_user_is_text(mock_db: MagicMock) -> None:
    html = await render_page(
        mock_db,
        "en",
        messages=[
            make_message("m1", "assistant", "[the guide](https://example.com/guide)"),
            make_message("m2", "user", "[mine](https://example.com/mine)"),
        ],
    )

    body = html.split("</style>")[1]
    assert '<div class="msg-body"><p><a href="https://example.com/guide">the guide</a></p>' in body
    assert body.count("<a ") == 1


async def test_a_link_with_a_script_scheme_is_not_made_an_anchor(mock_db: MagicMock) -> None:
    html = await render_page(mock_db, "en", messages=[make_message("m1", "assistant", "[x](javascript:alert(1))")])

    assert "<a " not in html.split("</style>")[1]


@pytest.mark.parametrize(
    ("text", "surface"),
    [
        (".time", ".msg.user"),
        (".time", ".msg.assistant"),
        (".footer", "body"),
        (".stat", "body"),
        (".model", ".model"),
        (".notice", ".notice"),
        (".msg-body blockquote", ".msg.assistant"),
        ("body", ".msg-body th"),
        (".msg-body a", ".msg.assistant"),
        (".msg-body a", ".msg-body th"),
    ],
    ids=[
        "time-on-user",
        "time-on-assistant",
        "footer",
        "stat",
        "model",
        "notice",
        "blockquote",
        "table-header",
        "link-in-assistant",
        "link-in-table-header",
    ],
)
@pytest.mark.parametrize("theme", ["light", "dark"])
async def test_small_text_is_readable_on_what_it_sits_on_in_both_themes(
    mock_db: MagicMock, text: str, surface: str, theme: Theme
) -> None:
    assert_readable(await render_page(mock_db, "en"), theme, text, surface)


@pytest.mark.parametrize("theme", ["light", "dark"])
async def test_the_table_header_is_shaded_differently_from_the_bubble_around_it(mock_db: MagicMock, theme: Theme) -> None:
    light, dark = split_themes(stylesheet(await render_page(mock_db, "en")))

    header = effective(light, dark, theme, ".msg-body th", "background")
    bubble = effective(light, dark, theme, ".msg.assistant", "background")

    assert header != bubble
