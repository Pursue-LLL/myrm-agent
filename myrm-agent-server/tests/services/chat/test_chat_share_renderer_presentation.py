"""Tests for how the shared conversation page presents tables and its small text."""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from tests.services.chat.share_support import agentless_db, make_message, render_page

_MIN_TEXT_CONTRAST = 4.5
_DARK_MEDIA = "@media(prefers-color-scheme:dark){"
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


def _theme_css(html: str) -> tuple[str, str]:
    """The page's (light, dark) stylesheet halves."""
    css = html.split("<style>")[1].split("</style>")[0]
    light, dark = css.split(_DARK_MEDIA)
    return light, dark


def _declared(css: str, selector: str, prop: str) -> str | None:
    """The hex value *selector* gives *prop* in *css* (the last rule wins), if it sets one."""
    pattern = rf"(?<![\w.\-]){re.escape(selector)}\{{[^}}]*?(?<=[{{;]){prop}:(#[0-9a-fA-F]{{6}})"
    found = re.findall(pattern, css)
    return found[-1] if found else None


def _luminance(hex_color: str) -> float:
    def channel(offset: int) -> float:
        value = int(hex_color[offset : offset + 2], 16) / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)


def _contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize(
    ("text", "backgrounds"),
    [(".time", (".msg.user", ".msg.assistant")), (".footer", ("body",)), (".model", (".model",))],
    ids=["time", "footer", "model"],
)
@pytest.mark.parametrize("theme", ["light", "dark"])
async def test_small_text_is_readable_on_what_it_sits_on_in_both_themes(
    mock_db: MagicMock, text: str, backgrounds: tuple[str, ...], theme: str
) -> None:
    light, dark = _theme_css(await render_page(mock_db, "en"))
    css = light if theme == "light" else dark

    for background in backgrounds:
        foreground = _declared(css, text, "color") or _declared(light, text, "color")
        surface = _declared(css, background, "background") or _declared(light, background, "background")
        assert foreground is not None
        assert surface is not None
        assert _contrast(foreground, surface) >= _MIN_TEXT_CONTRAST, (text, background, theme, foreground, surface)
