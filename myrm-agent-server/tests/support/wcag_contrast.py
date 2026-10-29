"""WCAG 2 text-contrast checks for tests that read the colours a rendered HTML page declares."""

from __future__ import annotations

import re
from typing import Literal

Theme = Literal["light", "dark"]

# WCAG 2.2 SC 1.4.3: normal-size text needs 4.5:1, compared unrounded.
MIN_TEXT_CONTRAST = 4.5

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
    """The colour the rule for exactly *selector* gives *prop* in *css* (the last rule wins), as ``#rrggbb``."""
    pattern = r"(?m)(?:^|(?<=\}))" + re.escape(selector) + r"\{[^}]*?(?<=[{;\s])" + re.escape(prop) + r":\s*" + _HEX
    found = re.findall(pattern, css)
    if not found:
        return None
    digits = found[-1]
    return "#" + (digits if len(digits) == 6 else "".join(digit * 2 for digit in digits)).lower()


def effective(light: str, dark: str, theme: Theme, selector: str, prop: str) -> str:
    """The colour *selector* paints *prop* with in *theme*: a dark rule overrides the light one, else the light one applies."""
    value = (declared(dark, selector, prop) if theme == "dark" else None) or declared(light, selector, prop)
    if value is None:
        raise AssertionError(f"{selector!r} declares no {prop} colour in the {theme} stylesheet")
    return value


def _luminance(hex_color: str) -> float:
    def channel(offset: int) -> float:
        value = int(hex_color[offset : offset + 2], 16) / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)


def contrast(foreground: str, background: str) -> float:
    """The WCAG contrast ratio of two ``#rrggbb`` colours, unrounded."""
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def assert_readable(html: str, theme: Theme, text: str, surface: str) -> None:
    """Fail unless *text*'s colour reaches ``MIN_TEXT_CONTRAST`` on *surface*'s background in *theme*."""
    light, dark = split_themes(stylesheet(html))
    foreground = effective(light, dark, theme, text, "color")
    background = effective(light, dark, theme, surface, "background")
    ratio = contrast(foreground, background)
    if ratio < MIN_TEXT_CONTRAST:
        raise AssertionError(f"{text} on {surface} in {theme}: {foreground} on {background} is {ratio:.2f}:1")
