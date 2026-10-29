"""WCAG 2 contrast checks for tests that read the colours a rendered HTML page declares.

[INPUT]
- the page's inline ``<style>`` block (POS: the server-rendered pages built by ``share_renderer``,
  ``share_password_page``, ``share_status_page``, the hosting ``decryptor_shell`` and the session export
  ``interactive_html_compiler``)

[OUTPUT]
- stylesheet / split_themes / declared / effective: read the colour a selector paints in the light or the dark theme;
  a page themed by custom properties (a ``:root`` block and one ``[data-theme="dark"]`` block) is read with each
  ``var(--name)`` resolved for the theme asked about
- single_hex / custom_properties / resolve_variables: the pieces ``declared`` and ``split_themes`` are built from
- declared_value: the raw text of one declaration, for checks that are not about a colour (an outline, an opacity)
- SINGLE_PALETTE / assert_single_palette: the theme a one-palette page is read as, and the guard that fails once a
  second palette appears
- contrast: the WCAG ratio of two colours
- assert_readable / assert_visible: the 4.5:1 check of a text colour, and the 3:1 check of a control's edge or focus
  mark, against the background they sit on

[POS]
Shared by the contrast tests of every server-rendered page, so each page is held to the same reading of its stylesheet
and the same bar. A stylesheet it cannot read raises instead of passing.
"""

from __future__ import annotations

import re
from typing import Literal

Theme = Literal["light", "dark"]

# A page without a prefers-color-scheme block has one palette; its single stylesheet is read as this theme.
SINGLE_PALETTE: Theme = "light"

# WCAG 2.2 SC 1.4.3: normal-size text needs 4.5:1, compared unrounded.
MIN_TEXT_CONTRAST = 4.5
# SC 1.4.11: a control's edge and its focus indicator need 3:1 against what they touch.
MIN_UI_CONTRAST = 3.0

_DARK_MEDIA = "@media(prefers-color-scheme:dark){"
_DARK_ATTRIBUTE = '[data-theme="dark"]'
_HEX = r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b"


def stylesheet(html: str) -> str:
    """The page's inline stylesheet."""
    return html.split("<style>")[1].split("</style>")[0]


def custom_properties(css: str, selector: str) -> dict[str, str]:
    """The ``--name: value`` declarations of the rule for exactly *selector* (the last declaration of a name wins)."""
    bodies = re.findall(r"(?m)(?:^|(?<=\}))\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return {name: value.strip() for body in bodies for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;}]*)", body)}


def resolve_variables(css: str, properties: dict[str, str]) -> str:
    """*css* with every ``var(--name)`` replaced by that property's value.

    A name no property holds is an error, and so is any ``var()`` left over afterwards (a fallback value, or a property
    defined by another variable): reading around it would report a colour the browser does not paint.
    """

    def value_of(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in properties:
            raise AssertionError(f"var({name}) is used but no rule declares {name}")
        return properties[name]

    resolved = re.sub(r"var\((--[\w-]+)\)", value_of, css)
    leftover = re.search(r"var\([^)]*\)?", resolved)
    if leftover:
        raise AssertionError(f"{leftover.group(0)!r} is a var() form this reader cannot resolve")
    return resolved


def split_themes(css: str) -> tuple[str, str]:
    """The (light, dark) halves of *css*: the dark half holds what its ``prefers-color-scheme: dark`` blocks declare.

    A page may instead theme itself with custom properties: a ``:root`` block holds the light values, a single
    ``[data-theme="dark"]`` block the dark ones, and each half has every ``var(--name)`` resolved for its theme.

    A colour-scheme block written in any other form would be read as light-theme rules and let a dark-theme
    regression pass, so one the helper cannot read is an error.
    """
    light, dark = _media_halves(css)
    attribute_rules = css.count(_DARK_ATTRIBUTE)
    if not attribute_rules:
        return light, dark
    overrides = custom_properties(css, _DARK_ATTRIBUTE)
    if attribute_rules != 1 or not overrides:
        raise AssertionError(f"a {_DARK_ATTRIBUTE} rule is only read as the one block of custom properties")
    if dark:
        raise AssertionError(f"the page is themed by both prefers-color-scheme and {_DARK_ATTRIBUTE}; use one")
    palette = custom_properties(css, ":root")
    return resolve_variables(light, palette), resolve_variables(light, {**palette, **overrides})


def _media_halves(css: str) -> tuple[str, str]:
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


def declared_value(css: str, selector: str, prop: str) -> str | None:
    """The text the rule for exactly *selector* gives *prop* in *css* (the last rule wins), or ``None`` if none does.

    The stylesheet may be minified or pretty-printed (indentation, a space before the brace); a rule for a longer or
    deeper selector (``button:hover``, ``.page button``) is a different rule.
    """
    pattern = r"(?m)(?:^|(?<=\}))\s*" + re.escape(selector) + r"\s*\{[^}]*?(?<=[{;\s])" + re.escape(prop) + r":([^;}]*)"
    found = re.findall(pattern, css)
    return found[-1].strip() if found else None


def declared(css: str, selector: str, prop: str) -> str | None:
    """The colour the rule for exactly *selector* gives *prop* in *css* (the last rule wins), as ``#rrggbb``.

    The value may be a shorthand around its colour (``border:1px solid #ddd``). A value that does not hold exactly one
    hex colour is an error, so a colour written in another notation can never read as not declared.
    """
    value = declared_value(css, selector, prop)
    return None if value is None else single_hex(value, f"{selector} gives {prop}")


def single_hex(value: str, where: str) -> str:
    """The one colour *value* holds, as ``#rrggbb``; anything else is an error that names *where* it was read."""
    colours = re.findall(_HEX, value)
    if len(colours) != 1:
        raise AssertionError(f"{where} {value!r}, which is not exactly one hex colour")
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


def assert_single_palette(html: str) -> None:
    """Fail when *html* declares a ``prefers-color-scheme`` block, so a second palette is never left unchecked."""
    if "prefers-color-scheme" in stylesheet(html):
        raise AssertionError(f"the page declares a prefers-color-scheme block; check each theme, not only {SINGLE_PALETTE}")


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
