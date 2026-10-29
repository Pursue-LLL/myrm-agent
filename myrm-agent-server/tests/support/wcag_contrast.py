"""WCAG 2 contrast checks for tests that read the colours a rendered HTML page declares.

[INPUT]
- the page's inline ``<style>`` block (POS: the server-rendered share pages built by ``share_renderer``,
  ``share_password_page`` and ``share_status_page``)

[OUTPUT]
- stylesheet / split_themes / declared / effective: read the colour a selector paints in the light or the dark theme
- contrast: the WCAG ratio of two colours
- assert_readable / assert_visible: the 4.5:1 check of a text colour, and the 3:1 check of a control's edge or focus
  mark, against the background they sit on

[POS]
Shared by the contrast tests of every share page, so each page is held to the same reading of its stylesheet and the
same bar. A stylesheet it cannot read raises instead of passing.
"""

from __future__ import annotations

import re
from typing import Literal

Theme = Literal["light", "dark"]

# WCAG 2.2 SC 1.4.3: normal-size text needs 4.5:1, compared unrounded.
MIN_TEXT_CONTRAST = 4.5
# SC 1.4.11: a control's edge and its focus indicator need 3:1 against what they touch.
MIN_UI_CONTRAST = 3.0

_DARK_MEDIA = "@media(prefers-color-scheme:dark){"
_HEX = r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b"


def stylesheet(html: str) -> str:
    """The page's inline stylesheet."""
    return html.split("<style>")[1].split("</style>")[0]


def split_themes(css: str) -> tuple[str, str]:
    """The (light, dark) halves of *css*: the dark half holds what its ``prefers-color-scheme: dark`` blocks declare.

    A colour-scheme block written in any other form would be read as light-theme rules and let a dark-theme
    regression pass, so one the helper cannot read is an error.
    """
    light: list[str] = []
    dark: list[str] = []
    at = 0
    while at < len(css):
        start = css.find(_DARK_MEDIA, at)
        if start < 0:
            light.append(css[at:])
            break
        light.append(css[at:start])
        body_start = start + len(_DARK_MEDIA)
        depth, end = 1, body_start
        while depth:
            depth += (css[end] == "{") - (css[end] == "}")
            end += 1
        dark.append(css[body_start : end - 1])
        at = end
    if css.count("prefers-color-scheme") != len(dark):
        raise AssertionError(f"a prefers-color-scheme block is not written as {_DARK_MEDIA!r}")
    return "".join(light), "".join(dark)


def declared(css: str, selector: str, prop: str) -> str | None:
    """The colour the rule for exactly *selector* gives *prop* in *css* (the last rule wins), as ``#rrggbb``.

    The value may be a shorthand around its colour (``border:1px solid #ddd``). A value that does not hold exactly one
    hex colour is an error, so a colour written in another notation can never read as not declared.
    """
    pattern = r"(?m)(?:^|(?<=\}))" + re.escape(selector) + r"\{[^}]*?(?<=[{;\s])" + re.escape(prop) + r":([^;}]*)"
    found = re.findall(pattern, css)
    if not found:
        return None
    colours = re.findall(_HEX, found[-1])
    if len(colours) != 1:
        raise AssertionError(f"{selector} gives {prop} {found[-1].strip()!r}, which is not exactly one hex colour")
    digits = colours[0]
    return "#" + (digits if len(digits) == 6 else "".join(digit * 2 for digit in digits)).lower()


def effective(light: str, dark: str, theme: Theme, selector: str, *props: str) -> str:
    """The colour *selector* paints with in *theme*: a dark rule overrides the light one, else the light one applies.

    *props* are alternative spellings of one property (``border-color`` or the ``border`` shorthand); the first one a
    stylesheet half declares wins.
    """
    for half in (dark, light) if theme == "dark" else (light,):
        for prop in props:
            if (value := declared(half, selector, prop)) is not None:
                return value
    raise AssertionError(f"{selector!r} declares no {'/'.join(props)} in the {theme} stylesheet")


def _luminance(hex_color: str) -> float:
    def channel(offset: int) -> float:
        value = int(hex_color[offset : offset + 2], 16) / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)


def contrast(foreground: str, background: str) -> float:
    """The WCAG contrast ratio of two ``#rrggbb`` colours, unrounded."""
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _assert_contrast(html: str, theme: Theme, mark: str, props: tuple[str, ...], surface: str, minimum: float) -> None:
    light, dark = split_themes(stylesheet(html))
    foreground = effective(light, dark, theme, mark, *props)
    background = effective(light, dark, theme, surface, "background")
    ratio = contrast(foreground, background)
    if ratio < minimum:
        raise AssertionError(
            f"{mark} {props[0]} on {surface} in {theme}: {foreground} on {background} is {ratio:.3f}:1, needs {minimum}"
        )


def assert_readable(html: str, theme: Theme, text: str, surface: str) -> None:
    """Fail unless *text*'s colour reaches ``MIN_TEXT_CONTRAST`` on *surface*'s background in *theme*."""
    _assert_contrast(html, theme, text, ("color",), surface, MIN_TEXT_CONTRAST)


def assert_visible(html: str, theme: Theme, mark: str, props: tuple[str, ...], surface: str) -> None:
    """Fail unless *mark*'s colour (read from *props*) reaches ``MIN_UI_CONTRAST`` on *surface*'s background in *theme*."""
    _assert_contrast(html, theme, mark, props, surface, MIN_UI_CONTRAST)
