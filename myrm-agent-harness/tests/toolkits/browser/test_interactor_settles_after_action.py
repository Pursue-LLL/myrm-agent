"""Which interactions end with the post-action settle: the ones that can make the page call its backend.

A click, a double click, typing, filling and a key press can submit, search or load; hovering, focusing, checking and
scrolling do not, so they do not hold the answer back. The settle itself is proven against a real page in
``test_post_action_settle_integration``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from patchright.async_api import Page

from myrm_agent_harness.toolkits.browser.session.interactor import Interactor
from myrm_agent_harness.toolkits.browser.snapshot import RefInfo

pytestmark = pytest.mark.asyncio

_REF_SETTLE = "myrm_agent_harness.toolkits.browser.session.interactor.settle_after_action"
_COORDINATE_SETTLE = "myrm_agent_harness.toolkits.browser.session.interactor_coord_mixin.settle_after_action"


@pytest.mark.parametrize(
    ("action", "text", "settles"),
    [
        ("click", "", True),
        ("dblclick", "", True),
        ("type", "hi", True),
        ("fill", "hi", True),
        ("press", "Enter", True),
        ("hover", "", False),
        ("focus", "", False),
        ("check", "", False),
        ("uncheck", "", False),
    ],
)
async def test_an_action_on_an_element_settles_only_when_it_can_ask_the_backend(
    action: str, text: str, settles: bool
) -> None:
    page = AsyncMock(spec=Page)
    interactor = Interactor(page, {"e0": RefInfo(role="textbox", name="field", nth=0)})

    with (
        patch("myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator", return_value=AsyncMock()),
        patch(_REF_SETTLE, new_callable=AsyncMock) as settle,
    ):
        await interactor.interact(action, "e0", text)

    if settles:
        settle.assert_awaited_once_with(page)
    else:
        settle.assert_not_awaited()


def _coordinate_page() -> MagicMock:
    page = MagicMock()
    page.viewport_size = {"width": 1280, "height": 720}
    page.mouse = MagicMock(move=AsyncMock(), click=AsyncMock(), dblclick=AsyncMock(), down=AsyncMock(), up=AsyncMock())
    page.keyboard = MagicMock(type=AsyncMock(), press=AsyncMock())
    return page


@pytest.mark.parametrize(
    ("action", "extra", "settles"),
    [
        ("click", {}, True),
        ("dblclick", {}, True),
        ("type", {"text": "hi"}, True),
        ("press", {"text": "Enter"}, True),
        ("drag", {"target_x": 500, "target_y": 400}, True),
        ("hover", {}, False),
    ],
)
async def test_an_action_at_coordinates_settles_only_when_it_can_ask_the_backend(
    action: str, extra: dict[str, object], settles: bool
) -> None:
    page = _coordinate_page()
    interactor = Interactor(page, {})

    with patch("asyncio.sleep", new=AsyncMock()), patch(_COORDINATE_SETTLE, new_callable=AsyncMock) as settle:
        await interactor.interact_at(action, 400, 300, **extra)

    if settles:
        settle.assert_awaited_once_with(page)
    else:
        settle.assert_not_awaited()
