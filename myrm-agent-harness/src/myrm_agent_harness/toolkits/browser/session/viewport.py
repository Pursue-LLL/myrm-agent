"""The area of a page that an interaction may point at.

[INPUT]
- patchright.async_api::Page (POS: the page whose visible area is measured)

[OUTPUT]
- page_viewport_size: (width, height) in CSS pixels

[POS]
Coordinate targeting, humanized mouse paths and scroll cursor placement all stay inside the viewport. A context that
emulates a viewport reports it; a context in the user's own browser emulates none and shows the window's own area,
which only the page can tell.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from patchright.async_api import Page

_FALLBACK_VIEWPORT = (1280, 720)


async def page_viewport_size(page: Page) -> tuple[int, int]:
    """The page's viewport: the emulated size when there is one, else the area the page measures for itself."""
    emulated = page.viewport_size
    if emulated is not None:
        return emulated["width"], emulated["height"]
    try:
        measured = await page.evaluate("[window.innerWidth, window.innerHeight]")
    except Exception:
        return _FALLBACK_VIEWPORT
    if (
        isinstance(measured, list)
        and len(measured) == 2
        and all(isinstance(side, int | float) and side > 0 for side in measured)
    ):
        return int(measured[0]), int(measured[1])
    return _FALLBACK_VIEWPORT
