"""The exported session page stays readable and keyboard-visible in both themes, and only a known theme reaches it.

[INPUT]
- InteractiveHtmlCompiler.compile_session and the stylesheet it inlines

[OUTPUT]
- pytest cases for text contrast, control edges and focus rings (WCAG 1.4.3, 1.4.11, 2.4.7) and for the theme option

[POS]
tests/services/session_export/test_interactive_html_compiler.py
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from app.services.session_export.export_types import ExportHtmlOptions, ExportTurnMessage
from app.services.session_export.interactive_html_compiler import InteractiveHtmlCompiler
from tests.support.wcag_contrast import Theme, assert_readable, assert_visible, declared_value, stylesheet

_THEMES: tuple[Theme, ...] = ("light", "dark")
_DRAWER = ".thinking-drawer, .tools-drawer"

_REPLY = """### Findings

Read the [design notes](https://example.com/notes) and `inline_code()` first.

| Name | Value |
| --- | --- |
| alpha | 1 |

```python
print("hello")
```
"""


def _compile(theme: str = "light", **overrides: str) -> str:
    messages = [
        ExportTurnMessage(role="user", content="Please review sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD", created_at="t0"),
        ExportTurnMessage(
            role="assistant",
            content=_REPLY,
            created_at="t1",
            thinking="Checking the files first.",
            tool_calls=[{"tool_name": "read_file", "arguments": "{}", "output": "ok"}],
        ),
    ]
    fields = {"chat_id": "chat-0123456789", "title": "Review", "agent_name": "AI Agent", **overrides}
    options = ExportHtmlOptions(theme=theme)  # type: ignore[arg-type]
    return InteractiveHtmlCompiler.compile_session(messages=messages, options=options, **fields).html_content


_PAGE = _compile()

# (text, surface): a text colour and the rule whose background it is painted on.
_TEXT_ON_SURFACE = {
    "page": ("body", "body"),
    "meta-line": (".meta-bar", "body"),
    "footer": (".footer", "body"),
    "button": (".btn", ".btn"),
    "button-hover": (".btn", ".btn:hover"),
    "search-text": (".search-input", ".search-input"),
    "search-placeholder": (".search-input::placeholder", ".search-input"),
    "agent-badge": (".badge-agent", ".badge-agent"),
    "sanitized-badge": (".badge-shield", ".badge-shield"),
    "user-label": (".role-badge.user", ".msg.user"),
    "assistant-label": (".role-badge.assistant", ".msg"),
    "timestamp-on-reply": (".timestamp", ".msg"),
    "timestamp-on-user-message": (".timestamp", ".msg.user"),
    "user-message": ("body", ".msg.user"),
    "reply": ("body", ".msg"),
    "thinking-text": (".thinking-content", _DRAWER),
    "drawer-title": ("body", _DRAWER),
    "tool-name": (".tool-badge", ".tool-call-item"),
    "tool-output": ("body", ".tool-detail pre"),
    "code-block": (".msg-content pre", ".msg-content pre"),
    "copy-button": (".copy-btn", ".copy-btn"),
    "copy-button-hover": (".copy-btn", ".copy-btn:hover"),
    "link-in-reply": (".msg-content a", ".msg"),
    "link-in-table-head": (".msg-content a", ".msg-content th"),
    "inline-code": ("body", ".msg-content code"),
    "table-head": ("body", ".msg-content th"),
}

# Every surface a focus ring can land on: the page, a message, a drawer or a table head.
_RING_SURFACES = ("body", ".msg", ".msg.user", _DRAWER, ".msg-content th")


@pytest.mark.parametrize("theme", _THEMES)
@pytest.mark.parametrize(("text", "surface"), _TEXT_ON_SURFACE.values(), ids=_TEXT_ON_SURFACE.keys())
def test_text_is_readable_on_the_surface_it_is_painted_on(theme: Theme, text: str, surface: str) -> None:
    assert_readable(_PAGE, theme, text, surface)


@pytest.mark.parametrize("theme", _THEMES)
@pytest.mark.parametrize("surface", ["body", ".search-input"])
def test_the_search_box_edge_is_visible_against_what_it_touches(theme: Theme, surface: str) -> None:
    assert_visible(_PAGE, theme, ".search-input", ("border",), surface)


@pytest.mark.parametrize("theme", _THEMES)
@pytest.mark.parametrize("surface", _RING_SURFACES)
def test_the_focus_ring_is_visible_on_every_surface_a_control_sits_on(theme: Theme, surface: str) -> None:
    assert_visible(_PAGE, theme, ":focus-visible", ("outline",), surface)


@pytest.mark.parametrize("theme", _THEMES)
def test_the_copy_button_ring_is_visible_against_the_button_it_is_drawn_inside(theme: Theme) -> None:
    assert_visible(_PAGE, theme, ".copy-btn:focus-visible", ("outline-color",), ".copy-btn")


def test_no_control_drops_its_focus_outline() -> None:
    css = stylesheet(_PAGE)

    assert not re.search(r"outline\s*:\s*(none|0)\b", css)
    assert (declared_value(css, ":focus-visible", "outline") or "").startswith("2px solid")


def test_the_controls_row_wraps_so_a_phone_does_not_scroll_sideways() -> None:
    assert declared_value(stylesheet(_PAGE), ".top-controls", "flex-wrap") == "wrap"


def test_every_code_block_is_the_box_its_copy_button_is_placed_in() -> None:
    css = stylesheet(_PAGE)

    assert declared_value(css, "pre", "position") == "relative"
    assert declared_value(css, ".copy-btn", "position") == "absolute"
    assert 'document.querySelectorAll("pre")' in _PAGE.replace("'", '"')


@pytest.mark.parametrize("theme", ["system", "light", "dark"])
def test_the_page_opens_in_the_theme_that_was_asked_for(theme: str) -> None:
    assert f'<html lang="en" data-theme="{theme}">' in _compile(theme)


@pytest.mark.parametrize("theme", ["", "Dark", 'dark"><script>alert(1)</script>', "sepia"])
def test_a_theme_outside_the_three_known_ones_is_refused_before_it_reaches_the_page(theme: str) -> None:
    with pytest.raises(ValidationError):
        ExportHtmlOptions(theme=theme)  # type: ignore[arg-type]


def test_text_that_came_from_the_session_never_becomes_markup() -> None:
    hostile = "<img src=x onerror=alert(1)>"
    messages = [
        ExportTurnMessage(
            role="user",
            content=hostile,
            created_at=hostile,
            thinking=hostile,
            tool_calls=[{"tool_name": hostile, "arguments": hostile, "output": hostile}],
        )
    ]

    page = InteractiveHtmlCompiler.compile_session(
        chat_id=hostile, title=hostile, agent_name=hostile, messages=messages, options=ExportHtmlOptions()
    ).html_content

    assert "<img" not in page
